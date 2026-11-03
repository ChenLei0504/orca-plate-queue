"""Explicit verification-code login. No password, credential discovery or redirects."""
import json
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

    def _post(self, url, payload):
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     'User-Agent': 'OrcaPlateQueue/0.8.0'}, method='POST')
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
            code = exc.code
            exc.close()
            if code == 429:
                raise CloudLoginError('请求过于频繁，请稍后再试。') from None
            if code == 403:
                raise CloudLoginError('云端拒绝了登录请求，请检查账号地区或稍后重试。') from None
            if code in (400, 401):
                raise CloudLoginError('账号或验证码无效，请重新获取验证码。') from None
            raise CloudLoginError('登录服务暂时不可用，请稍后重试。') from None
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
        result = self._post(url, body)
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
