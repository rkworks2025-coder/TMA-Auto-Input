import sys
import os
import time
import datetime
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 設定エリア
# ==========================================
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"
EVIDENCE_DIR = "evidence"

# ==========================================
# 厳格な操作関数 (Fail Fast: エラー隠蔽なし)
# ==========================================
def get_chrome_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1')
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def take_screenshot(driver, name):
    if not os.path.exists(EVIDENCE_DIR): os.makedirs(EVIDENCE_DIR)
    timestamp = datetime.datetime.now().strftime('%H%M%S')
    driver.save_screenshot(f"{EVIDENCE_DIR}/{name}_{timestamp}.png")

def click_strict(driver, selector):
    by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.CSS_SELECTOR
    el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by, selector)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    time.sleep(0.5)
    el.click()

def input_strict(driver, selector, value):
    sel = selector if (selector.startswith("#") or "." in selector) else f"#{selector}"
    el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
    el.clear()
    el.send_keys(str(value))
    if str(el.get_attribute('value')) != str(value):
        raise Exception(f"Input mismatch: {sel}")

# ==========================================
# メインプロセス
# ==========================================
def main():
    target_plate = sys.argv[1] if len(sys.argv) > 1 else ""
    target_login_url = sys.argv[2] if (len(sys.argv) > 2 and sys.argv[2]) else DEFAULT_LOGIN_URL
    driver = get_chrome_driver()

    try:
        # --- [1] ログイン ---
        driver.get(target_login_url)
        input_strict(driver, "cardNo1", TMA_ID.split("-")[0])
        input_strict(driver, "cardNo2", TMA_ID.split("-")[1])
        input_strict(driver, "password", TMA_PW)
        click_strict(driver, ".btn-primary")
        
        # --- [1.5] 予約履歴へ ---
        click_strict(driver, "//main//a[contains(@href,'reserve')]")

        # --- [2] 車両リスト選択 & ポップアップ ---
        click_strict(driver, "(//div[contains(@class, 'other-btn-area')]//a[contains(text(), '点検')])[1]")
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "posupMessageConfirm")))
        click_strict(driver, "posupMessageConfirmOk")

        # --- [2.5] 点検トップ ---
        click_strict(driver, "#startBtnContainer a")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#dailyBtnContainer a")))
        click_strict(driver, "#dailyBtnContainer a")

        # --- [3] 日常点検データ取得 (GAS API) ---
        res = requests.get(f"{GAS_API_URL}?plate_full={target_plate}").json()
        if not res.get("ok"): raise Exception(f"GAS Error: {res.get('error')}")
        td = res.get("prev", {})

        # --- 【A】 タイヤ (Tab: tire) ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'タイヤ')]")
        click_strict(driver, "tireType1")
        input_strict(driver, "tireFrontRegularPressure", res.get("std_f", "240"))
        input_strict(driver, "tireRearRegularPressure", res.get("std_r", "240"))
        
        wheels = [("rf", "FrontRightCm"), ("lf", "FrontLeftCm"), ("lr", "RearLeftBi4"), ("rr", "RearRightBi4")]
        for pre, suf in wheels:
            input_strict(driver, f"tireMfr{suf}", str(td.get(f"dot_{pre}", "0123")).zfill(4))
            depth = str(td.get(f"tread_{pre}", "5.5")).split(".") + ["0"]
            input_strict(driver, f"tireGroove{suf}Ip", depth[0])
            input_strict(driver, f"tireGroove{suf}Fp", depth[1][0])
            p_val = td.get(f"pre_{pre}", "240")
            input_strict(driver, f"tirePressure{suf}", p_val)
            input_strict(driver, f"tirePressureAdjusted{suf}", p_val)
        click_strict(driver, "tireDamage1")

        # --- 【B】 動作確認 (Tab: motion) ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'動作')]")
        click_strict(driver, "engineCondition1")
        click_strict(driver, "brakeCondition1")
        click_strict(driver, "parkingBrakeCondition1")
        click_strict(driver, "washerSprayCondition1")
        click_strict(driver, "wiperWipeCondition1")

        # --- 【C】 車載品-運転席 (Tab: in-car) ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車載品(運転')]")
        click_strict(driver, "inspectionCertificateExist1")
        click_strict(driver, "inspectionStickerExist1")
        click_strict(driver, "autoLiabilityExist1")
        click_strict(driver, "maintenanceStickerExist1")
        click_strict(driver, "roomStickerExist1")
        click_strict(driver, "deodorantsExist1")

        # --- 【D】 装備確認 (Tab: equipment) ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'装備')]")
        click_strict(driver, "backMonitor1")
        click_strict(driver, "cornerSensor1")
        click_strict(driver, "brakeSupport1")
        click_strict(driver, "laneDevianceAlert1")
        click_strict(driver, "driveRecorder1")

        # --- 【E】 灯火 & 周り ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'灯火')]")
        click_strict(driver, "turnSignal1")
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車両周り')]")
        click_strict(driver, "fuelCap1")
        click_strict(driver, "carStickerExist1")

        # --- 【F】 車載品-トランク (Tab: trunk) ---
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車載品(トランク')]")
        click_strict(driver, "warningTrianglePlateDamage1")
        click_strict(driver, "puncRepairKitExist1")
        click_strict(driver, "cleaningKit1")

        # 日常点検完了
        click_strict(driver, "a.is-complete")
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 2. 車内清掃 ---
        click_strict(driver, "#interiorBtnContainer a")
        click_strict(driver, "interiorDirt1")
        click_strict(driver, "interiorCheckTrouble1")
        click_strict(driver, "soundVolume1")
        click_strict(driver, "lostArticle1")
        click_strict(driver, "a.is-complete")
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 3. 洗車 ---
        click_strict(driver, "#washBtnContainer a")
        click_strict(driver, "exteriorDirt2")
        click_strict(driver, "a.is-complete")
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 4. 外装確認 ---
        click_strict(driver, "#exteriorBtnContainer a")
        click_strict(driver, "exteriorState1")
        click_strict(driver, "a.is-complete")
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        print("=== SUCCESS: 全工程完了 ===")
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
