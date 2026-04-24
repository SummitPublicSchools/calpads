import logging
import os
import time
import traceback
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

import calpads.client
from calpads.client import CALPADSClient

logging.basicConfig(level=logging.INFO)

OUTPUT_DIR = Path("G:/Shared drives/Data & Analytics/Source Docs/Exports and Downloads/Pre-Cleaned Exports")
DEBUG_HTTP = True
PYTHONUNBUFFERED=1


def build_authenticated_session_via_playwright():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://www.calpads.org/", wait_until="domcontentloaded")

        print("\nComplete CALPADS login/MFA in the browser.")
        input("After you are fully logged in, press Enter here... ")

        cookies = context.cookies()

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

        for cookie in cookies:
            session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        browser.close()
        return session


def enable_http_debug(session):
    original_get = session.get
    original_post = session.post

    def debug_get(*args, **kwargs):
        requested_url = args[0] if args else kwargs.get("url")
        resp = original_get(*args, **kwargs)

        print(f"\n[DEBUG][GET] requested={requested_url}")
        print(f"[DEBUG][GET] final={resp.url}")
        print(f"status={resp.status_code}")

        try:
            print(resp.text[:1000])
        except Exception:
            pass

        return resp

    def debug_post(*args, **kwargs):
        requested_url = args[0] if args else kwargs.get("url")
        print(f"\n[DEBUG][POST] requested={requested_url}")
        print(f"[DEBUG][POST] data={kwargs.get('data')}")

        resp = original_post(*args, **kwargs)

        print(f"[DEBUG][POST] final={resp.url}")
        print(f"status={resp.status_code}")

        try:
            print(resp.text[:1000])
        except Exception:
            pass

        return resp

    #session.get = debug_get
    session.post = debug_post


def test_login(cc):
    try:
        resp = cc.session.get(
            "https://www.calpads.org/Extract",
            timeout=30,
            allow_redirects=True,
        )

        print(f"Login check URL: {resp.url}")
        print(f"Status: {resp.status_code}")

        text = resp.text.lower()

        good_markers = [
            "calpads | extract home",
            "/extract/odsextract",
            "realtime extracts",
            "extract home",
        ]

        bad_markers = [
            "interim dual login page",
            "identity.calpads.org",
            "forgot new username?",
            "login/openidconnect",
            "login/azureopenid",
        ]

        if resp.status_code == 200 and any(marker in text for marker in good_markers):
            print("CALPADS login/session looks valid.")
            return True

        if any(marker in text for marker in bad_markers):
            print("CALPADS session may not be authenticated.")
            print(resp.text[:1500])
            return False

        if resp.status_code == 200 and "extract home" in text and "/extract" in resp.url.lower():
            print("CALPADS login/session looks valid.")
            return True

        print("Unable to confirm authenticated session.")
        print(resp.text[:1500])
        return False

    except Exception as e:
        print(f"Error checking CALPADS login: {e}")
        print(traceback.format_exc())
        return False


def save_bytes_locally(data, output_path):
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as file_handle:
            file_handle.write(data)

        print(f"Saved to {output_path}")

    except Exception as e:
        print(f"Save failed for {output_path}: {e}")
        print(traceback.format_exc())


base_input = [
    ("RecordHistory", "Y"),
    ("School", "0000001"),
    ("School", "0000002"),
    ("StartDate", "07/01/2021"),
    ("EnrollmentStartDate", "07/01/2021"),
    ("EndDate", "06/30/2026"),
    ("EnrollmentEndDate", "06/30/2026"),
    ("SpecialEducationStatus", "1"),
    ("SpecialEducationStatus", "2"),
    ("SpecialEducationStatus", "3"),
    ("SpecialEducationStatus", "4"),
    ("CertificationStatusCode", "All"),
    ("EducationProgramCode", "All"),
    ("ActiveStudent", False),
]


def main():
    session = build_authenticated_session_via_playwright()

    cc = CALPADSClient(
        session=session
    )

    if DEBUG_HTTP:
        enable_http_debug(cc.session)

    if not test_login(cc):
        print("Stopping because login is invalid.")
        return "Login failed"

    extracts_map = {
        "SENR": "SENR",
        "SELA": "SELA",
        "SINF": "SINF",
        "SWDS": "SWDS",
        "SPRG": "SPRG",
        "DIRECTCERTIFICATION": "DirectCert",
    }

    lea_map = {
        "0126193": "MV",
        "0122556": "HW",
        "0140749": "EV",
        "0139832": "WV",
        "0126177": "SL",
    }

    for extract, filename in extracts_map.items():
        for lea_code, abbrev in lea_map.items():
            form_data = [("School", lea_code)] + base_input

            try:
                print("=================================================")
                print(f"Requesting {filename} for {abbrev}")
                print(f"Form Data: {form_data}")

                request_ok = cc.request_extract(
                    lea_code=lea_code,
                    extract_name=extract,
                    by_date_range=True,
                    form_data=form_data,
                )

                if not request_ok:
                    print(f"Request may have failed for {filename} / {abbrev}")
                    continue

                time.sleep(10)

                extract_bytes = cc.download_extract(
                    lea_code=lea_code,
                    return_bytes=True,
                    extract_name=extract
                )

                if not extract_bytes:
                    print(f"Download failed for {filename} / {abbrev}")
                    continue

                output_path = os.path.join(
                    OUTPUT_DIR,
                    f"{abbrev} - {filename}.txt",
                )

                save_bytes_locally(extract_bytes, output_path)

            except Exception as e:
                print(f"{filename} failed for {abbrev}: {e}")
                print(traceback.format_exc())

    print("Done")
    return "Done"


if __name__ == "__main__":
    main()