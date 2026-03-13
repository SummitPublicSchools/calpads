import requests
import logging
import json
import re
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, urljoin, urlparse
from collections import deque
from json import JSONDecodeError
from lxml import etree
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
from .reports_form import ReportsForm, REPORTS_DL_FORMAT
from .extracts_form import ExtractsForm
from .files_upload_form import FilesUploadForm

init(autoreset=True)

# -----------------------------------------------------------------------
# CIAM / Login constants
# -----------------------------------------------------------------------
_CIAM_TENANT  = "a5c37e77-5d3f-42b8-9d78-78c7c26edfc8"
_CIAM_BASE    = f"https://{_CIAM_TENANT}.ciamlogin.com"
_CLIENT_ID    = "f9c69f1f-661f-4e4b-836c-5d59c05d694d"
_CALPADS_LOGIN_URL = "https://www.calpads.org/login/AzureOpenId?returnUrl="

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


# -----------------------------------------------------------------------
# Module-level helpers (mirrors calpads_login.py top-level functions)
# -----------------------------------------------------------------------

class _ColorLogger:
    """Colored console logger. When debug=False only errors and successes print."""

    def __init__(self, debug: bool = False):
        self._debug = debug

    def info(self, msg):
        if self._debug:
            print(Fore.CYAN + "INFO: " + Style.RESET_ALL + str(msg))

    def debug(self, msg):
        if self._debug:
            print(Fore.WHITE + Style.DIM + "DEBUG: " + str(msg) + Style.RESET_ALL)

    def warning(self, msg):
        if self._debug:
            print(Fore.YELLOW + "WARNING: " + Style.RESET_ALL + str(msg))

    def error(self, msg):
        print(Fore.RED + "ERROR: " + Style.RESET_ALL + str(msg))

    def success(self, msg):
        print(Fore.GREEN + "SUCCESS: " + Style.RESET_ALL + str(msg))


def _extract_config(html: str) -> dict:
    match = re.search(r'\$Config\s*=\s*(\{.*?\});\s*//', html, re.DOTALL)
    if not match:
        raise ValueError("Could not find $Config in page.")
    return json.loads(match.group(1))


def _get_base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _dump_html(filename: str, url: str, html: str, debug: bool = False):
    if not debug:
        return
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"<!-- URL: {url} -->\n{html}")


def _follow_redirects_manually(session: requests.Session, url: str, log: _ColorLogger) -> requests.Response:
    """
    Follow redirects one at a time, explicitly capturing Set-Cookie headers
    on every hop — including cross-domain redirects where requests may
    silently drop cookies (e.g. calpads.org -> ciamlogin.com).
    """
    resp = None
    current_url = url
    for hop in range(20):
        log.info(f"  Hop {hop}: GET {current_url}")
        resp = session.get(
            current_url,
            allow_redirects=False,
            headers={**_BROWSER_HEADERS, "Referer": current_url if hop > 0 else ""},
        )

        domain = urlparse(current_url).netloc
        for c in resp.cookies:
            if not c.domain:
                session.cookies.set(c.name, c.value, domain=domain)

        log.info(f"  -> {resp.status_code} | Location: {resp.headers.get('Location', '-')}")

        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location.startswith("http"):
                location = _get_base_url(current_url) + location
            current_url = location
        else:
            break

    return resp


# -----------------------------------------------------------------------
# Main client
# -----------------------------------------------------------------------

class CALPADSClient:

    def __init__(self, username, password, debug: bool = False):
        self.host = "https://www.calpads.org/"
        self.username = username
        self.password = password
        self._debug = debug
        self.log = _ColorLogger(debug=debug)

        self.visit_history = deque(maxlen=10)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _BROWSER_HEADERS["User-Agent"]})

        # Attach event hook AFTER login so it doesn't interfere with the CIAM flow
        self._std_logger = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        logging.basicConfig(format=log_fmt, level=logging.INFO)

        try:
            self.__connection_status = self._login()
        except RecursionError:
            self._std_logger.info("Looks like the provided credentials might be incorrect. Confirm credentials.")

        # Wire up the lightweight visit-history hook only after login is complete
        self.session.hooks['response'].append(self._handle_event_hooks)

    # -------------------------------------------------------------------
    # Login  (ported 1-to-1 from calpads_login.py: login_to_calpads)
    # -------------------------------------------------------------------

    def _login(self) -> bool:
        """Login via Microsoft Entra CIAM. Returns True on success."""
        log = self.log
        session = self.session
        session.headers.update(_BROWSER_HEADERS)
        session.cookies.clear()
    
        # ------------------------------------------------------------------
        # STEP 1: Follow the redirect chain manually to diagnose where
        #         Microsoft sends us and what cookies get set along the way
        # ------------------------------------------------------------------
        log.info("=" * 60)
        log.info("Step 1: Following redirect chain from CALPADS login...")
        log.info("=" * 60)
    
        resp = _follow_redirects_manually(session, _CALPADS_LOGIN_URL, log)
        resp.raise_for_status()
        _dump_html("debug_step1.html", resp.url, resp.text, self._debug)
    
        ms_base = _get_base_url(resp.url)
        log.info(f"Final MS landing URL: {resp.url}")
    
        try:
            config = _extract_config(resp.text)
        except ValueError:
            _dump_html("debug_step1_noconfig.html", resp.url, resp.text, self._debug)
            raise RuntimeError(
                f"No $Config found on landing page. "
                f"Status={resp.status_code}, URL={resp.url}. "
                f"Check debug_step1_noconfig.html"
            )
    
        hpgid = config.get("hpgid")
        pgid = config.get("pgid", "unknown")
        log.info(f"hpgid={hpgid}, pgid={pgid}, sessionId={config.get('sessionId')}")
        log.info(f"urlPost={config.get('urlPost')}")
        log.info(f"sErrorCode={config.get('sErrorCode', 'none')}")
        log.info(f"arrValErrs={config.get('arrValErrs', [])}")
    
        # ---------------------------------------------------------------
        # If we're on hpgid=6 (KMSI/BssoInterrupt), Microsoft thinks we
        # already authenticated. This is caused by sso cookies being set
        # during the redirect chain from a prior SSO session on the server.
        #
        # The sErrorCode=50058 in the config means "session expired /
        # needs reauthentication" — we need to follow urlPost (which is
        # the full OAuth2 authorize URL) to restart the auth flow cleanly,
        # this time telling Microsoft to force a fresh login via prompt=login.
        # ---------------------------------------------------------------
        if hpgid == 6:
            log.warning(
                f"Landed on hpgid=6 ({pgid}). "
                "Microsoft is short-circuiting to KMSI. "
                "Restarting from CALPADS with a fully fresh session..."
            )
    
            # We MUST restart from CALPADS — not just from Microsoft — because:
            # 1. CALPADS sets .AspNetCore.Correlation.* and .AspNetCore.OpenIdConnect.Nonce.*
            #    cookies tied to a specific nonce/state pair on the first redirect.
            # 2. Adding prompt=login to the existing Microsoft URL creates a new nonce/state
            #    but the CALPADS cookies still reference the OLD flow — causing a 500.
            # Solution: clear everything and restart from CALPADS so both the
            # CALPADS cookies and the Microsoft flow are in sync.
    
            session = requests.Session()
            session.headers.update(_BROWSER_HEADERS)
            session.cookies.clear()
            self.session = session
    
            # Append prompt=login directly to the CALPADS login URL so that
            # ASP.NET Core passes it through in the OAuth2 redirect to Microsoft.
            calpads_prompt_url = _CALPADS_LOGIN_URL + "&prompt=login" if "?" in _CALPADS_LOGIN_URL else _CALPADS_LOGIN_URL + "?prompt=login"
            # ASP.NET Core OpenIdConnect middleware forwards extra query params,
            # but the safest approach is to just hit the base URL fresh —
            # the new session will have no SSO cookies so Microsoft will prompt.
            log.info(f"Restarting from CALPADS with clean session: {_CALPADS_LOGIN_URL}")
    
            resp = _follow_redirects_manually(session, _CALPADS_LOGIN_URL, log)
            resp.raise_for_status()
            _dump_html("debug_step1_retry.html", resp.url, resp.text, self._debug)
    
            try:
                config = _extract_config(resp.text)
            except ValueError:
                raise RuntimeError(
                    "No $Config after clean restart. "
                    "Check debug_step1_retry.html"
                )
    
            hpgid = config.get("hpgid")
            pgid = config.get("pgid", "unknown")
            log.info(f"After clean restart: hpgid={hpgid}, pgid={pgid}")
    
            # If still on hpgid=6 even with a clean session, Microsoft has an
            # SSO session server-side. Force it with prompt=login on the authorize URL.
            if hpgid == 6:
                log.warning("Still hpgid=6 after clean session — adding prompt=login to authorize URL")
                authorize_url = config.get("urlPost", "")
                if not authorize_url.startswith("http"):
                    authorize_url = ms_base + authorize_url
                if "prompt=" in authorize_url:
                    authorize_url = re.sub(r'[&?]prompt=[^&]*', '', authorize_url)
                sep = "&" if "?" in authorize_url else "?"
                authorize_url = authorize_url + sep + "prompt=login"
                log.info(f"prompt=login authorize URL: {authorize_url}")
    
                # Clear only Microsoft cookies, keep the CALPADS correlation cookies
                for c in list(session.cookies):
                    if "ciamlogin.com" in c.domain or "microsoftonline.com" in c.domain:
                        session.cookies.clear(domain=c.domain, path=c.path, name=c.name)
    
                resp = _follow_redirects_manually(session, authorize_url, log)
                resp.raise_for_status()
                _dump_html("debug_step1_prompt_login.html", resp.url, resp.text, self._debug)
    
                try:
                    config = _extract_config(resp.text)
                except ValueError:
                    raise RuntimeError("Still no $Config after prompt=login. Check debug_step1_prompt_login.html")
    
                hpgid = config.get("hpgid")
                pgid = config.get("pgid", "unknown")
                log.info(f"After prompt=login: hpgid={hpgid}, pgid={pgid}")
    
            ms_base = _get_base_url(resp.url)
    
        if hpgid != 11406:
            log.warning(
                f"Expected hpgid=11406 (FabricLogin) but got hpgid={hpgid} ({pgid}). "
                "Will attempt to continue anyway."
            )
    
        # Extract tokens from whichever config we ended up with
        sft = config.get("sFT", "")
        canary = config.get("canary", "")
        s_ctx = config.get("sCtx", "")
        session_id = config.get("sessionId", "")
        correlation_id = config.get("correlationId", "")
    
        url_post = config.get("urlPost", "")
        if not url_post.startswith("http"):
            url_post = ms_base + url_post
    
        # If urlPost is still the OAuth2 authorize URL (not the login handler),
        # rewrite it to the tenant login endpoint
        if "/oauth2/v2.0/authorize" in url_post or (
            "/login?" in url_post and "client_id=" in url_post
        ):
            url_post = f"{_CIAM_BASE}/{_CIAM_TENANT}/login"
            log.info(f"urlPost was OAuth2 authorize, rewrote to: {url_post}")
    
        credential_type_url = (
            config.get("urlGetCredentialType")
            or f"{_CIAM_BASE}/common/GetCredentialType?mkt=en-US"
        )
    
        # ------------------------------------------------------------------
        # STEP 2: GetCredentialType
        # ------------------------------------------------------------------
        log.info("Step 2: GetCredentialType...")
        cred_resp = session.post(
            credential_type_url,
            json={
                "username": self.username,
                "isOtherIdpSupported": True,
                "checkPhones": False,
                "isRemoteNGCSupported": True,
                "isCookieBannerShown": False,
                "isFidoSupported": True,
                "originalRequest": s_ctx,
                "flowToken": sft,
            },
            headers={**_BROWSER_HEADERS, "Content-Type": "application/json"},
        )
        cred_resp.raise_for_status()
        cred_data = cred_resp.json()
        log.info(f"GetCredentialType ThrottleStatus={cred_data.get('ThrottleStatus')}")
    
        if cred_data.get("Credentials", {}).get("FederationRedirectUrl"):
            raise NotImplementedError("Account is federated to external IdP.")
    
        new_sft = cred_data.get("FlowToken")
        if new_sft:
            sft = new_sft
            log.info("Updated flowToken from GetCredentialType.")
    
        # ------------------------------------------------------------------
        # STEP 3: POST password
        # ------------------------------------------------------------------
        log.info(f"Step 3: POSTing password to {url_post}...")
    
        password_payload = {
            "i13": "0",
            "login": self.username,
            "loginfmt": self.username,
            "type": "11",
            "LoginOptions": "3",
            "lrt": "",
            "lrtPartition": "",
            "hisRegion": "",
            "hisScaleUnit": "",
            "passwd": self.password,
            "ps": "2",
            "flowToken": sft,
            "canary": canary,
            "ctx": s_ctx,
            "hpgrequestid": session_id,
            "PPSX": "",
            "NewUser": "1",
            "FoundMSAs": "",
            "fspost": "0",
            "i21": "0",
            "CookieDisclosure": "0",
            "IsFidoSupported": "1",
            "isSignupPost": "0",
            "i2": "1",
            "i17": "0",
            "i18": "__DefaultSAML_1__",
            "i19": "10000",
            "client_id": _CLIENT_ID,
        }
    
        pw_resp = session.post(
            url_post,
            data=password_payload,
            allow_redirects=True,
            headers={**_BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        )
        _dump_html("debug_step3.html", pw_resp.url, pw_resp.text, self._debug)
        pw_resp.raise_for_status()
    
        if (
            "your account or password is incorrect" in pw_resp.text.lower()
            or "that microsoft account doesn't exist" in pw_resp.text.lower()
        ):
            raise ValueError("Login failed: incorrect username or password.")
    
        log.info(f"Password POST landed at: {pw_resp.url}")
    
        # ------------------------------------------------------------------
        # STEP 4: Walk intermediate Microsoft pages (KMSI etc.)
        # ------------------------------------------------------------------
        current_html = pw_resp.text
        current_url = pw_resp.url
    
        for attempt in range(6):
            soup = BeautifulSoup(current_html, "html.parser")
            form = soup.find("form")
    
            if form:
                action = form.get("action", "")
                if "calpads.org" in action or "azure-signin-oidc" in action:
                    log.info("Found OIDC callback form.")
                    break
    
            # Also check raw HTML for the OIDC callback action in case
            # the form action is embedded in a script or not parsed correctly
            if "azure-signin-oidc" in current_html or (
                "calpads.org" in current_html and "id_token" in current_html
            ):
                log.info("Found OIDC data in raw HTML — extracting via regex.")
                # Find the form action via regex
                action_match = re.search(
                    r'<form[^>]+action=["\'](.*?)["\'][^>]*>', current_html
                )
                if action_match:
                    form_action = action_match.group(1)
                    if "azure-signin-oidc" in form_action or "calpads.org" in form_action:
                        break
    
            try:
                inter_config = _extract_config(current_html)
            except ValueError:
                log.warning("No $Config — trying raw form submit.")
                if form:
                    action = form.get("action", "")
                    if not action.startswith("http"):
                        action = _get_base_url(current_url) + action
                    payload = {
                        inp.get("name"): inp.get("value", "")
                        for inp in form.find_all("input") if inp.get("name")
                    }
                    r = session.post(action, data=payload, allow_redirects=True)
                    r.raise_for_status()
                    _dump_html(f"debug_step4_{attempt}.html", r.url, r.text, self._debug)
                    current_html, current_url = r.text, r.url
                else:
                    log.error("No form and no $Config.")
                    break
                continue
    
            page_id = inter_config.get("hpgid")
            inter_url_post = inter_config.get("urlPost", "")
            if not inter_url_post.startswith("http"):
                inter_url_post = _get_base_url(current_url) + inter_url_post
            log.info(f"Intermediate hpgid={page_id}, urlPost={inter_url_post}")
    
            if page_id in (6, 28, 1115) or "kmsi" in inter_url_post.lower():
                log.info(f"Handling KMSI/interrupt page (hpgid={page_id})...")
                o_post_params = inter_config.get("oPostParams", {})
                if o_post_params:
                    kmsi_payload = dict(o_post_params)
                elif page_id == 1115:
                    # hpgid=1115 is KmsiInterrupt (React page, no HTML form).
                    # POST to /kmsi with type=28, LoginOptions=0 to click Yes/stay signed in.
                    kmsi_payload = {
                        "LoginOptions": "0",
                        "type": "28",
                        "ctx": inter_config.get("sCtx", ""),
                        "hpgrequestid": inter_config.get("sessionId", ""),
                        "flowToken": inter_config.get("sFT", ""),
                        "canary": inter_config.get("canary", ""),
                        "DontShowAgain": "true",
                        "i19": "2000",
                    }
                else:
                    kmsi_payload = {
                        "LoginOptions": "3",
                        "type": "28",
                        "ctx": inter_config.get("sCtx", ""),
                        "hpgrequestid": inter_config.get("sessionId", ""),
                        "flowToken": inter_config.get("sFT", inter_config.get("flowToken", "")),
                        "canary": inter_config.get("canary", ""),
                        "DontShowAgain": "true",
                        "i19": "5000",
                    }
                r = session.post(
                    inter_url_post, data=kmsi_payload, allow_redirects=True,
                    headers={**_BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                )
                r.raise_for_status()
                _dump_html(f"debug_step4_{attempt}.html", r.url, r.text, self._debug)
                current_html, current_url = r.text, r.url
                log.info(f"Post-KMSI: {r.url}")
    
            else:
                log.warning(f"Unknown intermediate hpgid={page_id}, trying form submit...")
                if form:
                    action = form.get("action", "")
                    if not action.startswith("http"):
                        action = _get_base_url(current_url) + action
                    payload = {
                        inp.get("name"): inp.get("value", "")
                        for inp in form.find_all("input") if inp.get("name")
                    }
                    r = session.post(action, data=payload, allow_redirects=True)
                    r.raise_for_status()
                    _dump_html(f"debug_step4_{attempt}.html", r.url, r.text, self._debug)
                    current_html, current_url = r.text, r.url
                else:
                    log.error("No form on intermediate page.")
                    break
    
        # ------------------------------------------------------------------
        # STEP 5: POST OIDC callback to CALPADS
        # ------------------------------------------------------------------
        log.info("Step 5: OIDC callback to CALPADS...")
    
        soup_final = BeautifulSoup(current_html, "html.parser")
        oidc_form = soup_final.find("form")
    
        if not oidc_form:
            _dump_html("debug_oidc_fail.html", current_url, current_html, self._debug)
            raise RuntimeError(
                "Could not find the OIDC callback form. "
                f"Check debug_oidc_fail.html | Last URL: {current_url}"
            )
    
        oidc_action = oidc_form.get("action", "")
    
        # Extract input values using regex directly on raw HTML to avoid
        # BeautifulSoup mangling JWT token values (base64url chars like +, =, /)
        oidc_payload = {}
        for m in re.finditer(
            r'<input[^>]+name=["\'](.*?)["\'][^>]+value=["\'](.*?)["\'][^>]*/?>'
            r'|<input[^>]+value=["\'](.*?)["\'][^>]+name=["\'](.*?)["\'][^>]*/?>'
            r'|<input[^>]+name=["\'](.*?)["\'][^>]*/?>'
            , current_html, re.DOTALL
        ):
            g = m.groups()
            if g[0] and g[1] is not None:
                oidc_payload[g[0]] = g[1]
            elif g[2] is not None and g[3]:
                oidc_payload[g[3]] = g[2]
            elif g[4]:
                oidc_payload[g[4]] = ""
    
        # Fallback: also grab any values BeautifulSoup found that regex missed
        for inp in oidc_form.find_all("input"):
            name = inp.get("name")
            if name and name not in oidc_payload:
                oidc_payload[name] = inp.get("value", "")
    
        log.info(f"OIDC action: {oidc_action}")
        log.info(f"OIDC payload keys: {list(oidc_payload.keys())}")
        for k, v in oidc_payload.items():
            log.info(f"  {k} = {str(v)[:80]}")
    
        missing = {"code", "id_token", "state", "session_state"} - set(oidc_payload.keys())
        if missing:
            log.warning(f"OIDC payload missing: {missing}")
    
        # Encode carefully — preserve the exact token bytes
        encoded_payload = urlencode(oidc_payload)
        log.info(f"Encoded payload length: {len(encoded_payload)} chars")
    
        # Log cookies being sent to CALPADS — the correlation cookie must be present
        log.info("Cookies being sent to calpads.org:")
        for c in session.cookies:
            if "calpads" in c.domain or c.domain == "":
                log.info(f"  [{c.domain}] {c.name} = {c.value[:60]}")
    
        # Log ALL cookies for full diagnosis
        log.info("All session cookies:")
        for c in session.cookies:
            log.info(f"  [{c.domain}] {c.name} = {c.value[:60]}")
    
        oidc_headers = {
            **_BROWSER_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"https://{_CIAM_TENANT}.ciamlogin.com",
            "Referer": current_url,
        }
        log.info(f"POSTing to: {oidc_action}")
        log.info(f"With headers: { {k: v for k, v in oidc_headers.items()} }")
    
        final_resp = session.post(
            oidc_action,
            data=encoded_payload,
            allow_redirects=False,  # Don't follow redirects so we see the raw response
            headers=oidc_headers,
        )
        log.info(f"OIDC POST raw status: {final_resp.status_code}")
        log.info(f"OIDC POST response headers: {dict(final_resp.headers)}")
        _dump_html("debug_step5_raw.html", final_resp.url, final_resp.text, self._debug)
    
        # Now follow redirects manually
        if final_resp.status_code in (301, 302, 303, 307, 308):
            redirect_url = final_resp.headers.get("Location", "")
            if not redirect_url.startswith("http"):
                redirect_url = "https://www.calpads.org" + redirect_url
            log.info(f"Following redirect to: {redirect_url}")
            final_resp = session.get(redirect_url, allow_redirects=True, headers=_BROWSER_HEADERS)
        elif final_resp.status_code == 500:
            raise RuntimeError(
                f"500 on azure-signin-oidc (empty body). "
                f"This is likely an ASP.NET antiforgery/correlation cookie mismatch. "
                f"Cookies sent: {[(c.name, c.domain) for c in session.cookies]}"
            )
        else:
            final_resp.raise_for_status()
        _dump_html("debug_step5.html", final_resp.url, final_resp.text, self._debug)
        log.info(f"Final URL: {final_resp.url}")
    
        # ------------------------------------------------------------------
        # STEP 6: Accept Terms of Service if presented
        # ------------------------------------------------------------------
        if 'calpads.org/tos' in final_resp.url or '/tos' in final_resp.text.lower():
            log.info('Step 6: Accepting Terms of Service...')
            tos_resp = session.post(
                'https://www.calpads.org/tos/accept',
                data='',
                allow_redirects=True,
                headers={
                    **_BROWSER_HEADERS,
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Content-Length': '0',
                    'Origin': 'https://www.calpads.org',
                    'Referer': 'https://www.calpads.org/tos',
                    'Sec-Fetch-Site': 'same-origin',
                },
            )
            tos_resp.raise_for_status()
            log.info(f'TOS accepted, redirected to: {tos_resp.url}')
            final_resp = tos_resp
    
        # ------------------------------------------------------------------
        # STEP 7: Verify
        # ------------------------------------------------------------------
        logged_in = any(
            k in final_resp.text.lower()
            for k in ("logout", "sign out", "logoff", "welcome")
        )
        if logged_in:
            log.success("Login successful!")
        else:
            log.warning("Could not confirm login — check debug_step5.html")
    
        return logged_in


    @property
    def is_connected(self):
        """User exposed attribute to check whether the client successfully connected. Might return false positives."""
        return self.__connection_status #Unclear, but there is a chance this returns a false positive

    def get_leas(self):
        """Returns the list of LEAs provided by CALPADS
        Returns:
            list of LEA dictionaries with the keys Disabled, Group, Selected, Text, Value
        """
        response = self.session.get(urljoin(self.host, 'Leas?format=JSON'))
        return safe_json_load(response)

    def get_all_schools(self, lea_code):
        """Returns the list of schools for the provided lea_code

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.

        Returns:
            list of School dictionaries with the keys Disabled, Group, Selected, Text, Value
        """
        response = self.session.get(urljoin(self.host, f"/SchoolListingAll?lea={lea_code}&format=JSON"))
        return safe_json_load(response)

    def get_submitter_names(self, lea_code):
        """Returns the list of users who might have ever submitted data for the provided lea_code

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.

        Returns:
            list of users dictionaries with the keys Disabled, Group, Selected, Text, Value
        """
        response = self.session.get(urljoin(self.host, f"/GetSubmitterNames?leaCdsCode={lea_code}&format=JSON"))
        return safe_json_load(response)

    def get_user_orgs(self, lea_code, email):
        """Returns a user's organization and their different roles. Can be used to reliably fetch UserOrgId.

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            email (str): an email of the user to lookup

        Returns:
            a dictionary object with a Data key which lists the user's available organizations
        """
        self._select_lea(lea_code)
        response = self.session.get(urljoin(self.host, f"/GetUserOrgs/{email}?format=JSON"))
        if response.status_code == 200:
            return safe_json_load(response)
        else:
            return json.loads('{"Data": [],"Total Count": 0}')

    def get_homepage_important_messages(self):
        """Returns the CALPADS' Homepage Important Messages section in JSON
        Returns:
            a dict with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, '/HomepageImportantMessages?format=JSON&skip=0&take=5&undefined=0'))
        self.log.debug(safe_json_load(response).get('Data'))
        return safe_json_load(response)

    def get_homepage_anomaly_status(self):
        """Returns the CALPADS' Homepage Anomaly Status section in JSON format
        Returns:
            a dict with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, '/HomepageAnomalyStatus?format=JSON'))
        return safe_json_load(response)

    def get_homepage_certification_status(self):
        """Returns the CALPADS' Homepage Certification Status section in JSON format
        Returns:
            a dict with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, '/HomepageCertificationStatus?format=JSON'))
        return safe_json_load(response)

    def get_homepage_submission_status(self):
        """Returns the CALPADS' Homepage Submission Status section in JSON format
        Returns:
            a dict with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, '/HomepageSubmissions?format=JSON'))
        return safe_json_load(response)

    def get_homepage_extract_status(self):
        """Returns the CALPADS' Homepage Extract Status section in JSON format
        Returns:
            a dict with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, '/HomepageNotifications?format=JSON'))
        return safe_json_load(response)

    def get_enrollment_history(self, ssid):
        """Returns a JSON object with the Enrollment history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Enrollment?format=JSON'))
        return safe_json_load(response)

    def get_demographics_history(self, ssid):
        """Returns a JSON object with the Demographics history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Demographics?format=JSON'))
        return safe_json_load(response)

    def get_address_history(self, ssid):
        """Returns a JSON object with the Address history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Address?format=JSON'))
        return safe_json_load(response)

    def get_elas_history(self, ssid):
        """Returns a JSON object with the English Language Acquisition Status (ELAS) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/EnglishLanguageAcquisition?format=JSON'))
        return safe_json_load(response)

    def get_program_history(self, ssid):
        """Returns a JSON object with the Program history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Program?format=JSON'))
        return safe_json_load(response)

    def get_student_course_section_history(self, ssid):
        """Returns a JSON object with the Student Course Section history (SCSE, SCSC) for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentCourseSection?format=JSON'))
        return safe_json_load(response)

    def get_cte_history(self, ssid):
        """Returns a JSON object with the Career Technical Education (CTE) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/CareerTechnicalEducation?format=JSON'))
        return safe_json_load(response)

    def get_stas_history(self, ssid):
        """Returns a JSON object with the Student Absence Summary (STAS) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentAbsenceSummary?format=JSON'))
        return safe_json_load(response)

    def get_sirs_history(self, ssid):
        """Returns a JSON object with the Student Incident Result (SIRS) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentIncidentResult?format=JSON'))
        return safe_json_load(response)

    def get_soff_history(self, ssid):
        """Returns a JSON object with the Student Offense (SOFF) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Offense?format=JSON'))
        return safe_json_load(response)

    def get_assessment_history(self, ssid):
        """Returns a JSON object with the Student Offense (SOFF) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Assessment?format=JSON'))
        return safe_json_load(response)

    def get_sped_history(self, ssid):
        """Returns a JSON object with the Student Special Education Archive (SPED) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SPED?format=JSON'))
        return safe_json_load(response)

    def get_serv_history(self, ssid):
        """Returns a JSON object with the Special Education Services (SERV) history for the provided SSID
        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier
        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SERV?format=JSON'))
        return safe_json_load(response)

    def get_swds_history(self, ssid):
        """Returns a JSON object with the Students with Disabilities Status (SWDS) history for the provided SSID
        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier
        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SWDS?format=JSON'))
        return safe_json_load(response)

    def get_ssrv_history(self, ssid):
        """Returns a JSON object with the Student Special Education Services Archive (SSRV) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SSRV?format=JSON'))
        return safe_json_load(response)

    def get_meet_history(self, ssid):
        """Returns a JSON object with the Special Education Meetings (MEET) history for the provided SSID
        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier
        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/MEET?format=JSON'))
        return safe_json_load(response)

    def get_psts_history(self, ssid):
        """Returns a JSON object with the Postsecondary Transition Status (PSTS) history for the provided SSID

        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/PSTS?format=JSON'))
        return safe_json_load(response)

    def get_plan_history(self, ssid):
        """Returns a JSON object with the Special Education Plans (PLAN) history for the provided SSID
        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier
        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary).
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/PLAN?format=JSON'))
        return safe_json_load(response)

    def get_plan_record_details(self, ssid, plan_key):
        """Returns a dictionary with specific fields from a single Special Education Plans (PLAN) record
        Args:
            ssid (int, str): the 10 digit CALPADS Statewide Student Identifier
            plan_key (int, str): the 7 digit PLAN record identifier
        Returns:
            a Dictionary with the General Education Participation Percentage and Special Transport Indicator
        """
        self.session.get(urljoin(self.host, f'student/{ssid}/PLAN/{plan_key}'))
        root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser())
        return {
            "GeneralEducationParticipationPercentage": self._get_input_value(root, "GeneralEducationParticipationPercentage"),
            "SpecialTransportationIndicator": self._get_radio_value(root, "SpecialTransportationIndicator")
        }

    def get_requested_extracts(self, lea_code):
        """Returns a dictionary object with the a list of extracts at the provided lea_code

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary)
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Extract?SelectedLEA={lea_code}&format=JSON'))
        return safe_json_load(response)

    def get_staff_demographics_history(self, seid):
        """Returns any existing staff demographics history for the provided SEID
        Args:
            seid(int, str): the 10 digit CALPADS Statewide Education Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary)
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Staff/{seid}/StaffDemographics?format=JSON'))
        return safe_json_load(response)

    def get_staff_assignments_history(self, seid):
        """Returns any existing staff assignments history for the provided SEID
        Args:
            seid(int, str): the 10 digit CALPADS Statewide Education Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary)
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Staff/{seid}/StaffAssignments?format=JSON'))
        return safe_json_load(response)

    def get_staff_courses_history(self, seid):
        """Returns any existing staff courses history for the provided SEID
        Args:
            seid(int, str): the 10 digit CALPADS Statewide Education Identifier

        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary)
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Staff/{seid}/StaffCourses?format=JSON'))
        return safe_json_load(response)

    def download_report(self, lea_code, report_code, file_name=None, is_snapshot=False,
                        download_format='CSV', form_data=None, dry_run=False, url_override=None):
        """Download CALPADS ODS or Snapshot Reports

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            report_code (str): Currently supports all known reports. Expected format is a string e.g. '8.1', '1.17', and '1.18'.
                For reports that have letters in them, for example the 8.1 EOY3, expected input is '8.1eoy3' OR '8.1EOY3'.
                No spaces, all one word.
            file_name (str): the name of the file to pass to open(file_name, 'wb'). Assumes any subdirectories
                parent directories referenced in the file name already exist.
            is_snapshot (bool): when True downloads the Snapshot Report. When False, downloads the ODS Report.
            download_format (str): The format in which you want the download for the report.
                Currently supports: csv, excel, pdf, word, powerpoint, tiff, mhtml, xml, datafeed
            form_data (dict): the data that should be sent with the form request. Usually, all select fields for the
                form need to be provided. To see list of valid values, set dry_run=True.
            dry_run (bool): when False, it downloads the report. When True, it doesn't download the report and instead
                returns a dict with the form fields and their expected inputs.
            url_override (str): optional parameter to override _get_report_link() method with hardcoded url. Used for
                when a report url is not included on the ODS webpage.

        Returns:
            bool: True for a successful download of report, else False.
            dict: when dry_run=True, it returns a dict of the form fields and their expected inputs for report manipulation

        """
        if not REPORTS_DL_FORMAT.get(download_format.upper()):
            self.log.info('{} is not a supported reports download format. Try: {}'
                          .format(download_format, ' '.join(REPORTS_DL_FORMAT.keys())))
            raise Exception('Bad download format')
        if not file_name:
            file_name = 'data'
        with self.session as session:
            self._select_lea(lea_code)
            if url_override is None:
                report_url = self._get_report_link(report_code.lower(), is_snapshot)
            else:
                report_url = url_override
            if report_url:
                session.get(report_url)
            else:
                # TODO: Write a ReportNotFound exception in an exceptions.py module
                raise Exception("Report Not Found")
            report_page_root = etree.fromstring(self.visit_history[-1].text, parser=etree.HTMLParser(encoding='utf8'))
            iframe_url = report_page_root.xpath("//iframe[@src and not(contains(@src, 'KeepAlive'))]")[0].attrib['src']
            #self.log.debug(iframe_url)
            session.get(iframe_url)
            form = ReportsForm(self.visit_history[-1].text)
            if dry_run:
                return form.filtered_parse

            if form_data:
                formatted_form_data = form.get_final_form_data(form_data)
            else:
                self.log.warning("Most report forms require at least some input, especially for Select form fields.")
                formatted_form_data = form.get_final_form_data(dict())

            # TODO: Test how form data treats None or False diferently from empty string
            submitted_form_data = {k: v for k, v in formatted_form_data.items() if v != ''}

            self.log.debug('The form data about to be submitted: \n{}\n'.format(submitted_form_data))
            self.log.debug('These are the data keys about to be submitted: \n{}\n'.format(submitted_form_data.keys()))
            session.post(self.visit_history[-1].url, data=submitted_form_data)

            # Regex for grabbing the base, direct download URL for the report
            regex = re.compile('(?<="ExportUrlBase":")[^"]+(?=")')  # Look for text sandwiched between the lookbehind and
            # the lookahead, but EXCLUDE the double quotes (i.e. find the first double quotes as the upper limit of the text)

            split_query = None
            if regex.search(self.visit_history[-1].text):
                self.log.debug('Found ExportUrlBase in the URL')
                export_url_base = regex.search(self.visit_history[-1].text).group(0)
                scheme, netloc, path, query, frag = urlsplit(urljoin("https://reports.calpads.org",
                                                                     export_url_base)
                                                             .replace('\\u0026', '&')
                                                             .replace('%3a', ':')
                                                             .replace('%2f', '/'))
                split_query = parse_qsl(query)

            if split_query:
                self.log.info("Adding Format parameter to the URL")
                split_query.append(('Format', REPORTS_DL_FORMAT[download_format.upper()]))
                self.log.info("Rejoining the query elements again")
                report_dl_url = urlunsplit([scheme, netloc, path, urlencode(split_query), frag])
                session.get(report_dl_url)
                self.log.info("Fetched the report bytes.")
                # Cautionary Tale here if the content is compressed:
                # https://stackoverflow.com/a/50825553
                # Might need to revisit later
                with open(file_name, 'wb') as f:
                    f.write(self.visit_history[-1].content)
                    return True

            #If you made it this far, something went wrong.
            self.log.info("Failed to download the report.")
            return False

    def request_extract(self, lea_code, extract_name, form_data=None, by_date_range=False,
                        by_as_of_date=False, dry_run=False):
        """
        Request an extract with the extract_name from CALPADS.

        For Direct Certification Extract, pass in extract_name='DirectCertification'.
        For DSEA Extract, pass in extract_name='DSEAExtract'
        For the others, use their abbreviated acronym, e.g. SENR, SELA, etc.

        When dry_run is true, this returns a dict with suggestions for form_data inputs. The keys are the keys,
        the values are options for valid values. If the value is str, then any string is allowed. Date parameters
        will provide a value with formatting instructions (namely, MM/DD/YYYY). Select fields have dict values in
        the form of: {'FieldName': {'_allows_multiple': True, 'val1': 'internal_val'}. The expected input should
        look like form_data = [('FieldName', 'internal_val')], that is take the key of dict, and the value of the
        nested dict. 'val1' is the value dispalyed in the UI. If '_allows_multiple' is False, then only one of those
        field keys should be sent in the request. If '_allows_multiple' is True, then the key can have multiple values.
        A common example is schools: [('School', '0000001'), ('School', '0000002')] for NPS and Private schools.

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            extract_name (str): generally the four letter acronym of the extract. e.g. SENR, SELA, etc.
                For Direct Certification Extract, pass in extract_name='DirectCertification'.
                Spelling matters, capitalization does not. Silently fails if report name is unrecognized/not supported.
            form_data (list of iterables, optional): a list of the (key, value) pairs to send in the POST request body. To know
                which keys and values are expected, set dry_run=True. Technically optional, but will silently fail if
                a required key is missing.
            by_date_range (bool, optional): some extracts can be requested with a date range parameter.
                Set to True to use date range.
            by_as_of_date (bool, optional): used only in CENR to fill out the As of Date form. If by_date_range is True,
                this is ignored.
            dry_run (bool): when False, it downloads the report. When True, it doesn't download the report and instead
                returns a dict with the form fields and their expected inputs.
        Returns:
            bool: True if extract request was successful, False if it was not successful.
            dict: when dry_run=True, it returns a dict of the form fields and their expected inputs for report manipulation
        """
        extract_name = extract_name.upper()
        if not form_data:
            form_data = list()
        with self.session as session:
            self._select_lea(lea_code)
            # Direct URL access for each extract request with a few exceptions for atypical extracts
            # navigate to extract page
            if extract_name == 'SSID':
                session.get('https://www.calpads.org/Extract/SSIDExtract')
            elif extract_name == 'DIRECTCERTIFICATION':
                session.get('https://www.calpads.org/Extract/DirectCertificationExtract')
            elif extract_name == 'REJECTEDRECORDS':
                session.get('https://www.calpads.org/Extract/RejectedRecords')
            elif extract_name == 'CANDIDATELIST':
                session.get('https://www.calpads.org/Extract/CandidateList')
            elif extract_name == 'REPLACEMENTSSID':
                session.get('https://www.calpads.org/Extract/ReplacementSSID')
            elif extract_name == 'SPEDDISCREPANCYEXTRACT':
                session.get('https://www.calpads.org/Extract/SPEDDiscrepancyExtract')
            elif extract_name == 'DSEAEXTRACT':
                session.get('https://www.calpads.org/Extract/DSEAExtract')
            else:
                #TODO: Let's add some more validation layers here. Maybe through a separate extract module like reports or
                #a config file
                session.get('https://www.calpads.org/Extract/ODSExtract?RecordType={}'.format(extract_name))
            root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding='utf8'))

            #In the past, for SPED and SSRV extracts, CALPADS showed SELPA and NonSELPA form options.
            #They have either removed or only show by permission levels, so we won't add that extra layer, for now.
            if by_date_range:
                try:
                    if extract_name != 'CENR':
                        chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "Date")]')[0]
                    else:
                        chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "DateRange")]')[0]
                except IndexError:
                    self.log.info("There is no By Date Range request option. Falling back to the default form option.")
                    chosen_form = root.xpath('//form[contains(@action, "Extract") and not(contains(@action, "Date"))]')[0]
            elif extract_name == 'CENR' and by_as_of_date:
                chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "AsofDate")]')[0]
            else:
                chosen_form = root.xpath('//form[contains(@action, "Extract") and not(contains(@action, "Date"))]')[0]

            extracts_form = ExtractsForm(chosen_form)
            if dry_run:
                return extracts_form.get_parsed_form_fields()

            default_filled_fields = extracts_form.prefilled_fields.copy() #Safe to do shallow copy; list contents are immutable
            # print('default_filled_fields:', default_filled_fields)

            # Remove any tuples in the default_filled_fields whose keys appear in the user-provided form_data list
            if form_data is not None and dry_run == False:
                keys_in_form_data = {key for key, _ in form_data}
                keys_in_form_data.add('ReportingLEA') # This will be added below based on lea_code
                # print('keys_in_form_data:', keys_in_form_data)
                filtered_filled_fields = [item for item in default_filled_fields if item[0] not in keys_in_form_data]
                # print('filtered_filled_fields:', filtered_filled_fields)
            else:
                filtered_filled_fields = default_filled_fields

            filtered_filled_fields.extend(form_data + [('ReportingLEA', lea_code)])
            filled_fields = filtered_filled_fields

            # Text inputs are not able to submit multiple key values, particularly a problem for Date Range
            filled_fields = extracts_form._filter_text_input_fields(filled_fields)
            #self.log.debug('The submitted form data: {}'.format(filled_fields))
            if extract_name in ['REJECTEDRECORDS', 'CANDIDATELIST',
                                'SPEDDISCREPANCYEXTRACT', 'SSID']:
                check_submitter = [field for field in filled_fields if field[0] == 'Submitter' and field[1] is not None]
                if not check_submitter:
                    #If no submitter field is provided, default to the current user
                    filled_fields.extend([('Submitter', self._get_submitter_id(lea_code, self.username))])
                check_jobid = [field for field in filled_fields if field[0] == 'JobID' and field[1] is not None]
                if not check_jobid:
                    #If no jobid is provided, default to the latest job's job id
                    filled_fields.extend([('JobID', self.get_homepage_submission_status().get('Data')[-1]['JobID'])])

            # print('filled_fields:', filled_fields)

            #self.log.debug('Posting extract request to: {}'.format(urljoin(self.host, chosen_form.attrib['action'])))
            session.post(urljoin(self.host, chosen_form.attrib['action']),
                         data=filled_fields)
            self.log.info("Attempted to request the extract.")
            success_text = 'Extract request made successfully.  Please check back later for download.'
            request_response = etree.fromstring(self.visit_history[-1].text, parser=etree.HTMLParser(encoding='utf8'))
            try:
                #self.log.debug(request_response.xpath('//p')[0].text)
                success = (success_text == request_response.xpath('//p')[0].text)
            except IndexError:
                #self.log.debug('Was not able to find a paragraph tag')
                success = False

            return success

    def download_extract(self, lea_code, file_name=None, timeout=60, poll=10, return_bytes=False):
        """
        Download the file and give it the provided file_name.

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            file_name (str): the name of the file to pass to open(file_name, 'wb'). Assumes any subdirectories
                parent directories referenced in the file name already exist.
            timeout (int, optional): how long to wait for a completed extract request.
                Defaults to 60 seconds.
            poll (float, optional): this is how long to wait between polls to the API to check if the request is
                complete. This parameter is used in time.sleep(). Defaults to 10 seconds to respect the server, and
                enforces a minimum of 1 second.
            return_bytes (bool, optional): instead of writing to file and returning True,
                this will return bytes if a download would have been successful.

        Returns:
            bool: True for a successful download of report, else False.
            bytes: Bytes of a successful download of the report if return_bytes=True
        """
        if poll < 1:
            poll = 1
        if not file_name:
            file_name = 'data'
        #TODO: Check also for type and download date, all that good stuff
        with self.session as session:
            self._select_lea(lea_code)
            time_start = time.time()
            extract_request_id = None
            while (time.time() - time_start) < timeout:
                result = self.get_requested_extracts(lea_code).get('Data')
                # self.log.debug(result)
                #Currently only pulling the first result to check against, assuming it's the latest
                if result[0]['ExtractStatus'] == 'Complete':
                    extract_request_id = result[0]['ExtractRequestID']
                    self.log.info("Found an extract request ID")
                    break
                #Take a breather
                time.sleep(poll)
            if extract_request_id and not return_bytes:
                with open(file_name, 'wb') as f:
                    f.write(self._get_extract_bytes(extract_request_id))
                    return True
            elif extract_request_id and return_bytes:
                return self._get_extract_bytes(extract_request_id)
            else:
                self.log.info("Download request timed out. The download might have taken too long.")
                return False

    def upload_file(self, lea_code, file_path=None, form_data=None, dry_run=False):
        """
        Upload the file at file_path to CALPADS.

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            file_path (str): the path of the file to pass to open(file_name, 'rb'). Assumes any subdirectories
                parent directories referenced already exist.
            form_data (list of iterables, optional): a list of the (key, value) pairs to send in the POST request body. To know
                which keys and values are expected, set dry_run=True. Technically optional, but will silently fail if
                a required key is missing.
            dry_run (bool, optional): when False, it uploads the file. When True, it doesn't download the report and instead
                returns a dict with the form fields and their expected inputs.

        Returns:
            bool: True for a successful download of report, else False.
        """
        if not dry_run:
            assert file_path and form_data, "File Path and Form Data are required inputs."
        with self.session as session:
            self._select_lea(lea_code)
            session.get("https://www.calpads.org/FileSubmission/FileUpload")
            root = etree.fromstring(self.visit_history[-1].text,
                                    etree.HTMLParser(encoding='utf8'))
            root_form = root.xpath("//div[@id='fileUpload']//form")[0]
            upload_form = FilesUploadForm(root_form)
            if dry_run:
                return upload_form.get_parsed_form_fields()
            prefilled_form = upload_form.prefilled_fields.copy()
            prefilled_form.extend(form_data)
            prefilled_dict = dict(prefilled_form)
            cleaned_filled_form = {k: v for k,v in prefilled_dict.items() if v != '' and v is not None}
            with open(file_path, 'rb') as f:
                file_input = {'FilesUploaded[0].FileName': f}
                session.post(urljoin(self.visit_history[-1].url, root_form.attrib['action']),
                             files=file_input,
                             data=cleaned_filled_form)
                self.log.info("Attempted to upload the file.")
            response = etree.fromstring(self.visit_history[-1].text,
                                        etree.HTMLParser(encoding='utf8'))
            if response.xpath('//*[contains(@class, "alert alert-success")]'):
                return True
            else:
                return False

    def post_file(self, lea_code, ignore_rejections=False, get_errors=False,
                  submitter_email=None, timeout=180, poll=30):
        """
        Post the most recent file submission, optionally fetching errors and/or ignoring rejected records.

        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            ignore_rejections (bool, optional): If True, posts the file and disregards any rejected records. Ignored if
                there are no rejected records. Defaults to False.
            get_errors (bool, optional): If True, will fetch the rejected records extract for the latest job and return
                it as bytes in the second item of the tuple. This takes longer to do. Defaults to False.
            submitter_email (str, optional): when get_errors is True, one can override the current client username
                in the request to fetch rejected records. This might be useful if you are looking to post a file
                that was submitted by another account and get the errors from it if they exist.
            timeout (int, optional): how long to wait while checking if the file is ready to post AND when get_errors=True,
                how long to wait for the rejected records extract to download. This isn't cumulative - the timeout variable
                is simply re-used for each operation (so for timeout=60, if both operations take ~minute to
                complete successfully, the total time could be 120 seconds, not 60)
                Defaults to 60 seconds.
            poll (float, optional): this is how long to wait between polls to the API to check if the request is
                complete. This parameter is used in time.sleep(). Defaults to 30 seconds to respect the server, and
                enforces a minimum of 10 seconds.

        Returns:
            2 item tuple:
                bool: True for a successful file post else False.
                bytes: Bytes of the errors if get_errors=True or empty byte string.
        """
        if poll < 10:
            poll = 10
        errors = b''
        with self.session as session:
            self._select_lea(lea_code)
            start_time = time.time()
            while (time.time()-start_time) < timeout:
                #TODO: Need to check that this references the correct data and not stale data
                #Maybe 'Ready for Review' ensures the date is never stale?
                get_job_status = self.get_homepage_submission_status().get('Data')[-1]
                if get_job_status['SubmissionStatus'] == 'Ready for Review':
                    if get_job_status['Rejected'] == '0':
                        #safe to post
                        session.get(f"https://www.calpads.org/FileSubmission/Detail/{get_job_status['JobID']}")
                        if self._post_file_post_action().xpath('//*[contains(@class, "alert alert-success")]'):
                            self.log.info("Successfully posted the file.")
                            return True, errors
                        else:
                            self.log.info("Attempted and failed to post the file.")
                            return False, errors
                    elif get_job_status['Rejected'] != '0' and ignore_rejections:
                        #safe-ish to post
                        self.log.info("There were rejections, but ignoring those rejections.")
                        if get_errors:
                            errors = self._get_file_submission_rejections(lea_code,
                                                                          get_job_status['FileTypeCode']+'ERR',
                                                                          submitter_email, get_job_status['JobID'],
                                                                          timeout, poll)
                        session.get(f"https://www.calpads.org/FileSubmission/Detail/{get_job_status['JobID']}")
                        if self._post_file_post_action().xpath('//*[contains(@class, "alert alert-success")]'):
                            self.log.info("Successfully posted the file.")
                            return True, errors
                        else:
                            self.log.info("Attempted and failed to post the file.")
                            return False, errors
                    elif get_job_status['Rejected'] != '0' and not ignore_rejections:
                        if get_errors:
                            errors = self._get_file_submission_rejections(lea_code,
                                                                          get_job_status['FileTypeCode']+'ERR',
                                                                          submitter_email, get_job_status['JobID'],
                                                                          timeout, poll)
                        self.log.info("Unable to post the latest job because some records were rejected")
                        return False, errors
                else:
                    time.sleep(poll)
            self.log.info("Unable to post the latest job, timed out.")
            return False, errors

    def _get_file_submission_rejections(self, lea_code, record_type, submitter_email,
                                        job_id, timeout, poll):
        """Helper for getting the latest file submission's rejected records"""
        self.log.info("Attempting to fetch the latest submission's rejected records.")
        if submitter_email:
            #If an email is not None, try to get the submitter ID
            submitter_id = self._get_submitter_id(lea_code, submitter_email)
        else:
            submitter_id = None
        submitted_fields = [('LEA', lea_code), ('RecordType', record_type),
                            ('JobID', job_id), ('Submitter', submitter_id),
                            ('School', 'All')]
        success = self.request_extract(lea_code, 'REJECTEDRECORDS', submitted_fields)
        if success:
            self.log.info("Successfully requested the rejected records. Attempting download.")
            return self.download_extract(lea_code, timeout=timeout, poll=poll, return_bytes=True) or b'Failed dowloading extract errors'
        else:
            self.log.info("Failed to request the rejected records.")
            return b'Failed requesting extract errors'

    def _get_submitter_id(self, lea_code, submitter_email):
        """Tries to return a submitter ID. If it fails, returns the email."""
        submitter_names = self.get_submitter_names(lea_code)
        try:
            return [submitter['Value'] for submitter in submitter_names
                    if submitter['Text'] == submitter_email][0]
        except IndexError:
            self.log.debug("Could not find the id for the submitter email; will use the email as is.")
            return submitter_email

    def _post_file_post_action(self):
        """Helper to officially post a file."""
        root = etree.fromstring(self.visit_history[-1].text,
                                etree.HTMLParser(encoding='utf8'))
        form_root = root.xpath('//form[@action="/FileSubmission/Post"]')[0]
        inputs = FilesUploadForm(form_root).prefilled_fields + [('command', 'Post All')]
        input_dict = dict(inputs)
        self.session.post(urljoin(self.host, '/FileSubmission/Post'),
                       data=input_dict)
        self.log.info("Attempted to post all for this submission job.")
        response_root = etree.fromstring(self.visit_history[-1].text,
                                    etree.HTMLParser(encoding='utf8'))
        return response_root
    def _get_extract_bytes(self, extract_request_id):
        """Get the extract bytes by extract_request_id. Returns bytes."""
        self.session.get(urljoin(self.host, f'/Extract/DownloadLink?ExtractRequestID={extract_request_id}'))
        return self.visit_history[-1].content

    def _select_lea(self, lea_code):
        """Specifies the context of the requests to the provided lea_code.
        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
            this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.

        Returns:
            None
        """
        with self.session as session:
            session.get(self.host)
            page_root = etree.fromstring(self.visit_history[-1].text, parser=etree.HTMLParser(encoding='utf8'))
            orgchange_form = page_root.xpath("//form[contains(@action, 'UserOrgChange')]")[0]
            try:
                org_form_val = (orgchange_form
                                .xpath("//select/option[contains(text(), '{}')]".format(lea_code))[0]
                                .attrib.get('value'))
            except IndexError:
                self.log.info("The provided lea_code, {}, does not appear to exist for you."
                              .format(lea_code))
                raise Exception("Unable to switch to the provided LEA Code")

            request_token = orgchange_form.xpath("//input[@name='__RequestVerificationToken']")[0].get('value')

            session.post(urljoin(self.host, orgchange_form.attrib['action']),
                         data={'selectedItem': org_form_val,
                               '__RequestVerificationToken': request_token})

    def _get_report_link(self, report_code, is_snapshot=False):
        """Fetch and return the URL associated with the report_code"""
        with self.session as session:
            if is_snapshot:
                session.get('https://www.calpads.org/Report/Certification')
            else:
                session.get('https://www.calpads.org/Report/Realtime')
            response = self.visit_history[-1]
            if report_code == '8.1eoy3' and is_snapshot:
                return 'https://www.calpads.org/Report/Snapshot/8_1_StudentProfileList_EOY3_'
            else:
                root = etree.fromstring(response.text, parser=etree.HTMLParser(encoding='utf8'))
                elements = root.xpath("//*[@class='num-wrap-in']")
                for element in elements:
                    if report_code == element.text.lower():
                        return urljoin(self.host, element.xpath('./../../a')[0].attrib['href'])
                self.log.info("Failed to find the provided report code.")

    def _get_input_value(self, root, input_id: str):
        """Returns the value of an input element by its id"""
        nodes = root.xpath(f"//input[@id='{input_id}']")
        return nodes[0].get("value") if nodes else None
    
    def _get_radio_value(self, root, radio_name: str):
        """Returns the value of the checked radio button by its name."""
        nodes = root.xpath(f"//input[@type='radio' and @name='{radio_name}' and @checked]")
        return nodes[0].get("value") if nodes else None

    def _handle_event_hooks(self, r, *args, **kwargs):
        """This hook is executed with every HTPP request, primarily used to handle instances of OAuth Dance."""
        self.log.debug(("Response STATUS CODE: {}\nChecking hooks for: \n{}\n"
                        .format(r.status_code, r.url)
                        )
                       )
        scheme, netloc, path, query, frag = urlsplit(r.url)
        if path == '/Account/Login' and r.status_code == 200:
            self.log.debug("Handling /Account/Login")
            self.session.cookies.update(r.cookies.get_dict()) #Update the cookies for future requests
            init_root = etree.fromstring(r.text, parser=etree.HTMLParser(encoding='utf8'))
            # Filling the login form
            self.credentials['__RequestVerificationToken'] = (init_root
                                                              .xpath("//input[@name='__RequestVerificationToken']")[0]
                                                              .get('value'))

            self.credentials['ReturnUrl'] = (init_root
                                              .xpath("//input[@id='ReturnUrl']")[0]
                                              .get('value'))

            self.credentials['AgreementConfirmed'] = "True"

            # self.log.debug(self.credentials)
            # Was helpful in debugging bad username & password, but that should probably not hang out on the console :)
            self.session.post(r.url,
                              data=self.credentials
                              )

        elif path in ['/connect/authorize/callback', '/connect/authorize'] and r.status_code == 200:
            self.log.debug("Handling /connect/authorize/callback")
            self.session.cookies.update(r.cookies.get_dict()) #Update the cookies for future requests
            login_root = etree.fromstring(r.text, parser=etree.HTMLParser(encoding='utf8'))

            # Interstitial OpenID Page
            openid_form_data = {input_.attrib.get('name'): input_.attrib.get("value") for input_ in login_root.xpath('//input')}
            action_url = login_root.xpath('//form')[0].attrib.get('action')

            #A check for the when to try to join on self.host
            scheme, netloc, path, query, frag = urlsplit(action_url)
            if (not scheme and not netloc):
                self.session.post(urljoin(self.host, action_url),
                                  data=openid_form_data
                                )
            else:
                self.log.debug("Using the action URL from the OpenID interstitial page: {}"
                               .format(action_url))
                self.session.post(action_url,
                                  data=openid_form_data
                                  )
        else:
            self.log.debug("No response hook needed for: {}\n".format(r.url))
            self.visit_history.append(r)
            return r

def safe_json_load(response):
    try:
        return json.loads(response.content)
    except JSONDecodeError:
        return {}