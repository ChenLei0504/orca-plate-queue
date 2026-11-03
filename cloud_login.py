"""Explicit verification-code login. No password, credential discovery or redirects."""
import json
from http.cookies import SimpleCookie
import re
import socket
import ssl
import urllib.error
import urllib.request


class CloudLoginError(ValueError):
    def __init__(self, message, diagnostic=''):
        self.diagnostic = diagnostic
        super().__init__(message + ('（诊断：' + diagnostic + '）' if diagnostic else ''))


def _transport_error(exc, stage):
    # Fixed categories only: raw exception strings may contain account payloads,
    # URLs, proxy credentials or certificate details and must never reach the UI.
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if 'audit permission required' in str(reason):
        return CloudLoginError('Orca 尚未允许本次网络操作。授权后再试，无需修改网络设置。', stage + '/PERMISSION')
    if isinstance(reason, ssl.SSLCertVerificationError):
        return CloudLoginError('登录服务的证书校验失败，请检查系统时间和网络代理证书。', stage + '/TLS_CERTIFICATE')
    if isinstance(reason, ssl.SSLError):
        return CloudLoginError('与登录服务建立安全连接失败。', stage + '/TLS')
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return CloudLoginError('登录服务请求超时，发送结果尚不确定；请先检查是否收到验证码，勿连续重试。', stage + '/TIMEOUT')
    if isinstance(reason, socket.gaierror):
        return CloudLoginError('无法解析登录服务地址，请检查 DNS 或代理设置。', stage + '/DNS')
    if isinstance(reason, (ConnectionError, OSError)):
        return CloudLoginError('登录服务连接中断或被拒绝，请检查网络或代理。', stage + '/CONNECTION')
    return CloudLoginError('登录请求处理异常，请提供诊断编号。', stage + '/INTERNAL')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CloudLogin:
    def __init__(self, opener=None):
        self._opener = opener or urllib.request.build_opener(_NoRedirect())

    @staticmethod
    def account(region, account):
        if region not in ('CN', 'US'):
            raise CloudLoginError('请选择中国大陆或全球区。')
        if not isinstance(account, str) or len(account) > 254:
            raise CloudLoginError('请输入有效的邮箱或中国大陆手机号。')
        account = account.strip()
        phone = bool(re.fullmatch(r'1[3-9][0-9]{9}', account))
        email = bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', account))
        if not email and not (region == 'CN' and phone):
            raise CloudLoginError('请输入有效的邮箱或中国大陆手机号。')
        return account, phone

    @staticmethod
    def _http_error(exc, stage):
        code = exc.code
        try:
            # Read only for classification. Never display/log a response body,
            # cookies, account, OTP or server-supplied text.
            try:
                body = exc.read(65536).decode('utf-8', 'replace').lower()
            except Exception:
                body = ''
            challenge = (exc.headers or {}).get('cf-mitigated') == 'challenge'
        finally:
            exc.close()
        if code == 429:
            return CloudLoginError('请求过于频繁，请稍后再试。', stage + '/HTTP_' + str(code))
        if code == 403 and 'missing_cookie' in body:
            return CloudLoginError('验证码请求缺少网页校验信息（HTTP 403），请更新插件后重试。', stage + '/HTTP_' + str(code))
        if code == 403 and (challenge or 'cloudflare' in body or 'captcha' in body):
            return CloudLoginError('云端要求网页安全验证（HTTP 403），当前验证码接口无法完成，请勿反复重试。', stage + '/HTTP_' + str(code))
        if code == 403:
            return CloudLoginError('云端拒绝了认证请求（HTTP 403）；无法仅凭此状态判断账号或地区是否有误。', stage + '/HTTP_' + str(code))
        if code in (400, 401):
            return CloudLoginError('账号或验证码未通过校验，请核对输入。', stage + '/HTTP_' + str(code))
        return CloudLoginError('登录服务暂时不可用，请稍后重试。', stage + '/HTTP_' + str(code))

    def _sms_headers(self):
        # The CN website endpoint requires the same CSRF cookie/header pair as
        # its browser form. Obtain our own short-lived anonymous cookie; do not
        # discover or reuse browser/Orca sessions or bypass interactive challenges.
        request = urllib.request.Request('https://bambulab.cn/api/csrf',
            headers={'Accept': 'application/json', 'User-Agent': 'OrcaPlateQueue/0.8.0'})
        try:
            with self._opener.open(request, timeout=20) as response:
                if response.status != 204:
                    raise CloudLoginError('无法获取短信网页校验信息，请稍后重试。')
                cookie = SimpleCookie()
                for value in response.headers.get_all('Set-Cookie', []):
                    cookie.load(value)
                item = cookie.get('bbl_csrf_token')
                token = item.value if item else ''
                if not token or len(token) > 4096 or not re.fullmatch(r'[A-Za-z0-9_.%~+=/-]+', token):
                    raise CloudLoginError('无法获取短信网页校验信息，请稍后重试。')
                return {'Cookie': 'bbl_csrf_token=' + token, 'x-bbl-csrf-token': token}
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, 'SMS_CSRF') from None
        except CloudLoginError:
            raise
        except Exception as exc:
            raise _transport_error(exc, 'SMS_CSRF') from None

    def _post(self, url, payload, headers=None, *, stage='LOGIN', acknowledgement=False):
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     'User-Agent': 'OrcaPlateQueue/0.8.0', **(headers or {})}, method='POST')
        try:
            with self._opener.open(request, timeout=20) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise CloudLoginError('登录服务返回的信息过大。')
                status = getattr(response, 'status', 200)
                if acknowledgement and status == 204 and not raw.strip():
                    return {}
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise CloudLoginError('登录服务返回了非 JSON 响应，无法确认请求结果。',
                        stage + '/HTTP_' + str(status) + '/NON_JSON') from None
                if acknowledgement and isinstance(data, str) and data.strip().lower() in ('ok', 'success'):
                    return {}
                if not isinstance(data, dict):
                    shape = 'JSON_STRING' if isinstance(data, str) else 'JSON_SHAPE'
                    raise CloudLoginError('登录服务返回了不支持的数据格式，无法确认请求结果。',
                        stage + '/HTTP_' + str(status) + '/' + shape)
                return data
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, stage) from None
        except CloudLoginError:
            raise
        except Exception as exc:
            raise _transport_error(exc, stage) from None

    def send_code(self, region, account):
        account, phone = self.account(region, account)
        root = 'https://api.bambulab.cn' if region == 'CN' else 'https://api.bambulab.com'
        if phone:
            url = 'https://bambulab.cn/api/v1/user-service/user/sendsmscode'
            body = {'phone': account, 'type': 'codeLogin'}
        else:
            url = root + '/v1/user-service/user/sendemail/code'
            body = {'email': account, 'type': 'codeLogin'}
        result = self._post(url, body, self._sms_headers() if phone else None,
                            stage='SMS_SEND' if phone else 'EMAIL_SEND', acknowledgement=True)
        if result.get('code') not in (None, 0, '0'):
            raise CloudLoginError('验证码发送失败，请核对账号和地区。')

    def login(self, region, account, code):
        account, _ = self.account(region, account)
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code.strip()):
            raise CloudLoginError('请输入六位验证码。')
        root = 'https://api.bambulab.cn' if region == 'CN' else 'https://api.bambulab.com'
        result = self._post(root + '/v1/user-service/user/login',
                            {'account': account, 'code': code.strip()})
        # Only the SDK's documented auth fields cross the private pipe. Never send
        # profile fields that would prevent the SDK from resolving the true user ID.
        token = result.get('accessToken')
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise CloudLoginError('云端未返回有效登录会话，请重新获取验证码。')
        auth = {'accessToken': token}
        refresh = result.get('refreshToken')
        if isinstance(refresh, str) and len(refresh) <= 16384:
            auth['refreshToken'] = refresh
        for key in ('expiresIn', 'refreshExpiresIn'):
            value = result.get(key)
            if type(value) in (int, float) and 0 < value < 315360000:
                auth[key] = value
        return auth
