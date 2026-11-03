"""Explicit verification-code login. No password, credential discovery or redirects."""
import json
from http.cookies import SimpleCookie
import re
import urllib.error
import urllib.request


class CloudLoginError(ValueError):
    pass


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
    def _http_error(exc):
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
            return CloudLoginError('请求过于频繁，请稍后再试。')
        if code == 403 and 'missing_cookie' in body:
            return CloudLoginError('验证码请求缺少网页校验信息（HTTP 403），请更新插件后重试。')
        if code == 403 and (challenge or 'cloudflare' in body or 'captcha' in body):
            return CloudLoginError('云端要求网页安全验证（HTTP 403），当前验证码接口无法完成，请勿反复重试。')
        if code == 403:
            return CloudLoginError('云端拒绝了认证请求（HTTP 403）；无法仅凭此状态判断账号或地区是否有误。')
        if code in (400, 401):
            return CloudLoginError('账号或验证码未通过校验，请核对输入。')
        return CloudLoginError('登录服务暂时不可用，请稍后重试。')

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
            raise self._http_error(exc) from None
        except CloudLoginError:
            raise
        except Exception:
            raise CloudLoginError('无法获取短信网页校验信息，请稍后重试。') from None

    def _post(self, url, payload, headers=None):
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     'User-Agent': 'OrcaPlateQueue/0.8.0', **(headers or {})}, method='POST')
        try:
            with self._opener.open(request, timeout=20) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise CloudLoginError('登录服务返回的信息过大。')
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from None
        except CloudLoginError:
            raise
        except Exception:
            raise CloudLoginError('无法连接登录服务，请检查网络后重试。') from None

    def send_code(self, region, account):
        account, phone = self.account(region, account)
        root = 'https://api.bambulab.cn' if region == 'CN' else 'https://api.bambulab.com'
        if phone:
            url = 'https://bambulab.cn/api/v1/user-service/user/sendsmscode'
            body = {'phone': account, 'type': 'codeLogin'}
        else:
            url = root + '/v1/user-service/user/sendemail/code'
            body = {'email': account, 'type': 'codeLogin'}
        result = self._post(url, body, self._sms_headers() if phone else None)
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
