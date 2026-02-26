import os
import time
import csv
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# Configuration paths and output setup
SAVE_DIR = r"D:\PickleballReports2"
CSV_FILE = os.path.join(SAVE_DIR, "matches4.0.csv")
os.makedirs(SAVE_DIR, exist_ok=True)

# CSV schema for match metadata
CSV_HEADERS = [
    "MatchID", "Skill Level", "TeamA", "TeamB", 
    "TeamAScore", "TeamBScore", "Rallies", "Shots"
]

def init_csv():
    # Create CSV with headers if file does not exist
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

def append_to_csv(data_dict):
    # Append one match record to CSV
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(data_dict)

def get_existing_match_ids():
    # Load previously scraped match ids to avoid duplicates
    if not os.path.exists(CSV_FILE):
        return set()
    ids = set()
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("MatchID"):
                ids.add(row["MatchID"])
    return ids

def parse_aggregated_score(score_str):
    # Convert aggregated score string into total team scores
    matches = re.findall(r'(\d+)\s*[-–]\s*(\d+)', score_str)
    team_a = sum(int(a) for a, b in matches)
    team_b = sum(int(b) for a, b in matches)
    return team_a, team_b

# Save raw HTML report using Selenium
def save_report_with_selenium(driver, url):
    name = url.split("/")[-1]
    path = os.path.join(SAVE_DIR, name)
    if not os.path.exists(path):
        print(f"Saving: {name}")
        driver.get(url)
        time.sleep(2)
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        time.sleep(1)

def scrape_all_pages(start_url):
    # Initialize storage and resume state
    init_csv()
    existing_ids = get_existing_match_ids()
    
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(options=options)

    driver.get(start_url)
    time.sleep(2)
    page = 1

    # Expand table to show 100 rows per page
    try:
        length_dropdown = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "dt-length-0"))
        )
        Select(length_dropdown).select_by_value("100")
        time.sleep(2)
    except Exception as e:
        print("Failed to set 100 rows per page.")
        print(f"Error: {e}")
        driver.quit()
        return

    while True:
        print(f"Scraping page {page}...")
        time.sleep(2)

        # Collect table data before navigating away from page
        page_data_to_process = []
        
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        for row in rows:
            try:
                # Extract report link and match id
                link_elem = row.find_element(By.CSS_SELECTOR, "td.column-9 a")
                url = link_elem.get_attribute("href")
                match_id = url.split("/")[-1].replace(".html", "")
                
                # Extract metadata columns
                skill = row.find_element(By.CSS_SELECTOR, "td.column-2").text
                team_a = row.find_element(By.CSS_SELECTOR, "td.column-3").text
                team_b = row.find_element(By.CSS_SELECTOR, "td.column-4").text
                raw_score = row.find_element(By.CSS_SELECTOR, "td.column-5").text
                rallies = row.find_element(By.CSS_SELECTOR, "td.column-6").text
                shots = row.find_element(By.CSS_SELECTOR, "td.column-7").text
                
                # Aggregate set scores into total match score
                sa, sb = parse_aggregated_score(raw_score)

                page_data_to_process.append({
                    "url": url,
                    "data": {
                        "MatchID": match_id,
                        "Skill Level": skill,
                        "TeamA": team_a,
                        "TeamB": team_b,
                        "TeamAScore": sa,
                        "TeamBScore": sb,
                        "Rallies": rallies,
                        "Shots": shots
                    }
                })
            except Exception:
                continue
        
        # Process collected page data
        for item in page_data_to_process:
            # Write new matches to CSV
            if item["data"]["MatchID"] not in existing_ids:
                append_to_csv(item["data"])
                existing_ids.add(item["data"]["MatchID"])
            
            # Save raw HTML report
            save_report_with_selenium(driver, item["url"])

        # Move to next page if available
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.dt-paging-button.next[aria-label="Next"]'))
            )
            if "disabled" in next_button.get_attribute("class"):
                print("Reached last page.")
                break

            driver.execute_script("arguments[0].scrollIntoView();", next_button)
            next_button.click()

            # Wait until table refresh completes
            if rows:
                WebDriverWait(driver, 20).until(EC.staleness_of(rows[0]))
            page += 1
        except Exception as e:
            print("No next button or failed to click.")
            print(f"Error: {e}")
            break

    driver.quit()

# Run multiple passes to resume after interruptions
for _ in range(11):
    scrape_all_pages("https://pklmart.com/reports/")