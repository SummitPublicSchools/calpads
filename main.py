import logging
import time
import traceback
import requests
from calpads.client import CALPADSClient
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

OUTPUT_DIR = Path("G:/Shared drives/Data & Analytics/Source Docs/Exports and Downloads/Pre-Cleaned Exports/")


def build_authenticated_session_via_playwright():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(accept_downloads=True)
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

extracts_base_input = [
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
    ("ActiveStudent", False)
]

def main():
    session = build_authenticated_session_via_playwright()

    cc = CALPADSClient(session=session)
    enable_http_debug(cc.session)

    extracts_map = {
        "SENR": "SENR",
        "SELA": "SELA",
        #"SINF": "SINF",
        #"SWDS": "SWDS",
        #"SPRG": "SPRG",
        #"DIRECTCERTIFICATION": "DirectCert",
    }

    report_urls_map = {
        "Accountability/16_21_StudentswithDisabilities_OverduePlanReviewandReevaluationMeetingsStudentList": "16.21",
        #"Accountability/16_14_StudentswithDisabilitiesPlanStudentListbyDSEA": "16.14",
        #"Realtime/5_7_FosterYouthEnrolledStudentListrt": "5.7",
        #"Realtime/5_9_FormerFosterYouthEnrolledStudentListrt": "5.9",
    }

    lea_map = {
        #"0126193": "MV",
        #"0122556": "HW",
        #"0140749": "EV",
        "0139832": "WV",
        "0126177": "SL"
    }

    lea_schoolname_map = {
        #"MV": "Mar Vista",
        #"HW": "Hollywood",
        #"EV": "East Valley",
        "WV": "West Valley",
        "SL": "Silver Lake"
    }

    #get reports
    for report_url, report in report_urls_map.items():
        for lea_code, abbrev in lea_map.items():
            for abbrev, schoolname in lea_schoolname_map.items():

                try:
                    print("=================================================")
                    print(f"Downloading {report} for {abbrev}")

                    request_ok = cc.download_report(
                        lea_code=lea_code,
                        form_data=
                        {
                            "LEA": f"Citizens of the World Charter School {schoolname}",
                            "School": {f"Citizens of the World Charter School {schoolname}-{lea_code}":True},
                            "AsOfMonth": datetime.today().strftime("%B"),
                            "AsOfDay": str(datetime.today().day)
                        }
                        ,
                        report_code=report,
                        file_name=Path(OUTPUT_DIR) / f"{abbrev} - {report}.csv",
                        url_override=f"https://www.calpads.org/Report/{report_url}"
                    )

                    if not request_ok:
                        print(f"Request may have failed for {report} / {abbrev}")
                        continue

                except Exception as e:
                    print(f"{report} failed for {abbrev}: {e}")
                    print(traceback.format_exc())

    print(" Reports done")


    #get extracts
    for extract, filename in extracts_map.items():
        for lea_code, abbrev in lea_map.items():
            form_data = [("School", lea_code)] + extracts_base_input

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

                #time.sleep(10)

                #extract_bytes = cc.download_extract(
                #    lea_code=lea_code,
                #    file_name=Path(OUTPUT_DIR) / f"{abbrev} - {extract}.txt"
                #)

                #if not extract_bytes:
                #    print(f"Download failed for {filename} / {abbrev}")
                #    continue

            except Exception as e:
                print(f"{filename} failed for {abbrev}: {e}")
                print(traceback.format_exc())

    print(" Extracts done")
    return "Done!"


if __name__ == "__main__":
    main()