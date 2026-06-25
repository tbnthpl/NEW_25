
import html as html_escape
import logging
import os
import re

import requests

try:
    from defusedxml import ElementTree as ET
    from defusedxml.common import DefusedXmlException
except Exception:
    import xml.etree.ElementTree as ET

    class DefusedXmlException(Exception):
        pass

logger = logging.getLogger(__name__)

SOAP_ENDPOINT = os.environ.get(
    "AD_SOAP_ENDPOINT",
    "https://10.250.7.210:443/SSO/ADLogin.asmx",
)
SOAP_ACTION = os.environ.get("AD_SOAP_ACTION", "http://tempuri.org/userAttributes")

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "").strip().lower()
_NON_LOCAL_ENVIRONMENTS = frozenset({"uat", "pre", "preprod", "prod", "production", "prd"})
_IS_PROD_TIER = _ENVIRONMENT in _NON_LOCAL_ENVIRONMENTS

VERIFY_SSL = os.environ.get("AD_VERIFY_SSL", "false").lower() in ("true", "1", "yes")

TIMEOUT_SEC = int(os.environ.get("AD_TIMEOUT", "30"))
_AD_SKIP_RAW = os.environ.get("AD_SKIP", "false").lower() in ("true", "1", "yes")
AD_SKIP = _AD_SKIP_RAW and not _IS_PROD_TIER
if _AD_SKIP_RAW and not AD_SKIP:
    logger.warning(
        "AD_SKIP ignored: ENVIRONMENT=%r requires bank AD (local dev only).",
        _ENVIRONMENT or "(unset)",
    )
AD_DEBUG = os.environ.get("AD_DEBUG", "false").lower() in ("true", "1", "yes")

AD_LOOSE_SUCCESS = os.environ.get("AD_LOOSE_SUCCESS", "true").lower() in (
    "true",
    "1",
    "yes",
)


def _send_soap(envelope: str, headers: dict):
    try:
        resp = requests.post(
            SOAP_ENDPOINT,
            data=envelope.encode("utf-8"),
            headers=headers,
            timeout=TIMEOUT_SEC,
            verify=VERIFY_SSL,
        )
        return (resp.ok, resp.status_code, resp.text or "")
    except requests.RequestException as e:
        return (False, 0, str(e))


def _interpret_login_success(xml_text: str, http_status: int) -> bool:
    if http_status < 200 or http_status >= 300:
        return False

    if not xml_text or not xml_text.strip():
        return False

    xml_lower = xml_text.lower()
    if re.search(r"(<|\w+:)?fault\b", xml_lower):
        return False
    if any(bad in xml_lower for bad in ("<fault>", "soap:fault", "soap12:fault")):
        return False

    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException):
        return False

    all_text = " ".join([t.strip() for t in root.itertext() if t.strip()]).lower()

    def _tag_matches(el, name):
        if not el.tag:
            return False
        tag_lower = el.tag.lower()
        return tag_lower.endswith(name.lower()) or name.lower() in tag_lower

    for tag in ("isAuthenticated", "Authenticated", "IsAuthenticated", "authenticated"):
        for el in root.iter():
            if _tag_matches(el, tag):
                val = (el.text or "").strip().lower()
                if val in ("true", "1", "yes"):
                    return True
                if val in ("false", "0", "no"):
                    return False

    for tag in ("Status", "Result", "Outcome", "AuthStatus", "LoginResult", "AuthResult"):
        for el in root.iter():
            if _tag_matches(el, tag):
                val = (el.text or "").strip().lower()
                if "success" in val or val in ("ok", "valid", "true", "1"):
                    return True
                if any(bad in val for bad in ("fail", "invalid", "error", "unauth", "denied", "false")):
                    return False

    for tag in ("ErrorCode", "ErrCode", "Code", "Error"):
        for el in root.iter():
            if _tag_matches(el, tag):
                val = (el.text or "").strip()
                if val.isdigit():
                    return int(val) == 0

    if not AD_LOOSE_SUCCESS:
        return False

    common_ad_fields = (
        "samaccountname",
        "displayname",
        "mail",
        "userprincipalname",
        "givenname",
        "sn",
        "mobile",
        "employeeeid",
        "userattributes",
        "userattributesresult",
    )
    if any(field in all_text for field in common_ad_fields):
        if not re.search(
            r"\binvalid\b|\bfail\b|\berror\b|\bdenied\b|\bunauthor",
            all_text,
        ):
            logger.warning("AD success via loose heuristic (common-fields); tighten AD response shape.")
            return True

    if "true" in all_text and "false" not in all_text:
        if not re.search(r"\b(invalid|fail|error|denied|unauthor)\b", all_text):
            logger.warning("AD success via loose heuristic (true-without-false); tighten AD response shape.")
            return True

    return False


def validate_ad_credentials(username: str, password: str) -> bool:
    """
    Validate username/password against Bank AD SOAP endpoint.
    Returns True if AD authentication succeeds, False otherwise.
    Set AD_SKIP=true to bypass AD (local dev only - accepts any non-empty password).
    """
    username = (username or "").strip()
    password = password or ""

    if not username or not password:
        return False

    if AD_SKIP:
        logger.warning("AD_SKIP enabled - bypassing Bank AD validation (local dev only)")
        return True

    soap12_env = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"\n'
        ' xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">\n'
        "  <soap12:Body>\n"
        '    <userAttributes xmlns="http://tempuri.org/">\n'
        "      <username>{username}</username>\n"
        "      <password>{password}</password>\n"
        "    </userAttributes>\n"
        "  </soap12:Body>\n"
        "</soap12:Envelope>"
    ).format(
        username=html_escape.escape(username),
        password=html_escape.escape(password),
    )

    soap11_env = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"\n'
        ' xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "  <soap:Body>\n"
        '    <userAttributes xmlns="http://tempuri.org/">\n'
        "      <username>{username}</username>\n"
        "      <password>{password}</password>\n"
        "    </userAttributes>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>"
    ).format(
        username=html_escape.escape(username),
        password=html_escape.escape(password),
    )

    headers_11 = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": SOAP_ACTION,
    }
    headers_12 = {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"'
    }

    ok, status, xml_text = _send_soap(soap11_env, headers_11)
    result = _interpret_login_success(xml_text, status)

    if not result and status in (415, 405, 500) and status != 0:
        ok2, status2, xml_text2 = _send_soap(soap12_env, headers_12)
        status, xml_text = status2, xml_text2
        result = _interpret_login_success(xml_text, status)

    if AD_DEBUG and xml_text:
        logger.info("AD_DEBUG: http_status=%s, result=%s, response=%s", status, result, xml_text[:1000])

    if not result and status and xml_text:
        logger.warning("AD login failed: http_status=%s, response_snippet=%s", status, (xml_text or "")[:400])

    return result
