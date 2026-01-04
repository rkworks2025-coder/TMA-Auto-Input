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
TMA_ID = "0030-927583" [cite: 39]
TMA_PW = "Ccj-222223" [cite: 39]
# 巡回管理メイン GAS WebApp URL
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec" [cite: 37, 39]
EVIDENCE_DIR = "evidence"

# ==========================================
# 厳格な操作関数 (エラー隠蔽なし)
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
    """クリック不可なら即例外を投げ、テストを失敗させる"""
    by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.CSS_SELECTOR
    el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by, selector)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    time.sleep(0.5)
    el.click()

def input_strict(driver, selector, value):
    """入力不可、または反映値が不一致なら即例外を投げる"""
    sel = selector if (selector.startswith("#") or "." in selector) else f"#{selector}"
    el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
    el.clear()
    el.send_keys(str(value))
    # 入力後の検証
    if str(el.get_attribute('value')) != str(value):
        raise Exception(f"入力値不一致エラー: {sel} (期待:{value})")

# ==========================================
# メインプロセス
# ==========================================
def main():
    # 引数から車両ナンバーとURLを取得 [cite: 85]
    target_plate = sys.argv[1] if len(sys.argv) > 1 else ""
    target_login_url = sys.argv[2] if (len(sys.argv) > 2 and sys.argv[2]) else DEFAULT_LOGIN_URL
    driver = get_chrome_driver()

    try:
        # --- [1] ログイン工程 ---
        driver.get(target_login_url)
        input_strict(driver, "cardNo1", TMA_ID.split("-")[0])
        input_strict(driver, "cardNo2", TMA_ID.split("-")[1])
        input_strict(driver, "password", TMA_PW)
        click_strict(driver, ".btn-primary")
        
        # --- [1.5] 予約履歴への遷移 ---
        click_strict(driver, "//main//a[contains(@href,'reserve')]")

        # --- [2] 車両リスト選択 & ポップアップ ---
        # 1番上の点検ボタンを選択 [cite: 36]
        click_strict(driver, "(//div[contains(@class, 'other-btn-area')]//a[contains(text(), '点検')])[1]")
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "posupMessageConfirm")))
        click_strict(driver, "posupMessageConfirmOk")

        # --- [2.5] 点検トップ (開始処理) ---
        click_strict(driver, "#startBtnContainer a")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#dailyBtnContainer a")))
        click_strict(driver, "#dailyBtnContainer a")

        # --- [3] 日常点検データ取得 (GAS API) ---
        # plate_fullキーを使用して最新データを要求 [cite: 62, 85]
        res = requests.get(f"{GAS_API_URL}?plate_full={target_plate}").json()
        if not res.get("ok"):
            raise Exception(f"GASデータ取得失敗: {res.get('error')}")
        td = res.get("prev", {})

        # --- 【A】 タイヤ (Tab: tire) --- [cite: 1]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'タイヤ')]")
        click_strict(driver, "tireType1") # 1 (ノーマル) [cite: 3]
        input_strict(driver, "tireFrontRegularPressure", res.get("std_f", "240")) [cite: 4]
        input_strict(driver, "tireRearRegularPressure", res.get("std_r", "240")) [cite: 4]
        
        # 右前 [cite: 5]
        input_strict(driver, "tireMfrFrontRightCm", str(td.get("dot_rf", "0123")).zfill(4)) [cite: 6]
        input_strict(driver, "tireGrooveFrontRightCmIp", str(td.get("tread_rf", "5.5")).split(".")[0]) [cite: 7]
        input_strict(driver, "tireGrooveFrontRightCmFp", (str(td.get("tread_rf", "5.5")).split(".") + ["0"])[1][0]) [cite: 8]
        input_strict(driver, "tirePressureFrontRightCm", td.get("pre_rf", "240")) [cite: 8]
        input_strict(driver, "tirePressureAdjustedFrontRightCm", td.get("pre_rf", "240")) [cite: 9]

        # 左前 [cite: 5]
        input_strict(driver, "tireMfrFrontLeftCm", str(td.get("dot_lf", "0123")).zfill(4)) [cite: 6]
        input_strict(driver, "tireGrooveFrontLeftCmIp", str(td.get("tread_lf", "5.5")).split(".")[0]) [cite: 7]
        input_strict(driver, "tireGrooveFrontLeftCmFp", (str(td.get("tread_lf", "5.5")).split(".") + ["0"])[1][0]) [cite: 8]
        input_strict(driver, "tirePressureFrontLeftCm", td.get("pre_lf", "240")) [cite: 8]
        input_strict(driver, "tirePressureAdjustedFrontLeftCm", td.get("pre_lf", "240")) [cite: 9]

        # 左後 [cite: 5]
        input_strict(driver, "tireMfrRearLeftBi4", str(td.get("dot_lr", "0123")).zfill(4)) [cite: 6]
        input_strict(driver, "tireGrooveRearLeftBi4Ip", str(td.get("tread_lr", "5.5")).split(".")[0]) [cite: 7]
        input_strict(driver, "tireGrooveRearLeftBi4Fp", (str(td.get("tread_lr", "5.5")).split(".") + ["0"])[1][0]) [cite: 8]
        input_strict(driver, "tirePressureRearLeftBi4", td.get("pre_lr", "240")) [cite: 8]
        input_strict(driver, "tirePressureAdjustedRearLeftBi4", td.get("pre_lr", "240")) [cite: 9]

        # 右後 [cite: 5]
        input_strict(driver, "tireMfrRearRightBi4", str(td.get("dot_rr", "0123")).zfill(4)) [cite: 6]
        input_strict(driver, "tireGrooveRearRightBi4Ip", str(td.get("tread_rr", "5.5")).split(".")[0]) [cite: 7]
        input_strict(driver, "tireGrooveRearRightBi4Fp", (str(td.get("tread_rr", "5.5")).split(".") + ["0"])[1][0]) [cite: 8]
        input_strict(driver, "tirePressureRearRightBi4", td.get("pre_rr", "240")) [cite: 8]
        input_strict(driver, "tirePressureAdjustedRearRightBi4", td.get("pre_rr", "240")) [cite: 9]

        click_strict(driver, "tireDamage1") # 1 (OK) [cite: 10]

        # --- 【B】 動作確認 (Tab: motion) --- [cite: 11]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'動作')]")
        click_strict(driver, "engineCondition1") # 1 (OK) [cite: 12]
        click_strict(driver, "brakeCondition1") # 1 (OK) [cite: 12]
        click_strict(driver, "parkingBrakeCondition1") # 1 (OK) [cite: 12]
        click_strict(driver, "washerSprayCondition1") # 1 (OK) [cite: 13]
        click_strict(driver, "wiperWipeCondition1") # 1 (OK) [cite: 13]

        # --- 【C】 車載品-運転席 (Tab: in-car) --- [cite: 14]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車載品(運転')]")
        click_strict(driver, "inspectionCertificateExist1") # 1 (OK) [cite: 15]
        click_strict(driver, "inspectionStickerExist1") # 1 (OK) [cite: 16]
        click_strict(driver, "autoLiabilityExist1") # 1 (OK) [cite: 16]
        click_strict(driver, "maintenanceStickerExist1") # 1 (OK) [cite: 17]
        # 発炎筒/駐車パスカードはスキップ指示 [cite: 17, 18]
        click_strict(driver, "roomStickerExist1") # 1 (OK) [cite: 18]
        click_strict(driver, "deodorantsExist1") # 1 (OK) [cite: 19]

        # --- 【D】 装備確認 (Tab: equipment) --- [cite: 20]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'装備')]")
        click_strict(driver, "backMonitor1") # 1 (OK) [cite: 20]
        click_strict(driver, "cornerSensor1") # 1 (OK) [cite: 20]
        click_strict(driver, "brakeSupport1") # 1 (OK) [cite: 21]
        click_strict(driver, "laneDevianceAlert1") # 1 (OK) [cite: 21]
        click_strict(driver, "driveRecorder1") # 1 (OK) [cite: 22]

        # --- 【E】 灯火装置 & 車両周り --- [cite: 23]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'灯火')]")
        click_strict(driver, "turnSignal1") # 1 (OK) [cite: 23]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車両周り')]")
        click_strict(driver, "fuelCap1") # 1 (OK) [cite: 24]
        click_strict(driver, "carStickerExist1") # 1 (OK) [cite: 24]

        # --- 【F】 車載品-トランク (Tab: trunk) --- [cite: 25]
        click_strict(driver, "//div[contains(@class,'tab-button')][contains(.,'車載品(トランク')]")
        click_strict(driver, "warningTrianglePlateDamage1") # 1 (OK) [cite: 26]
        click_strict(driver, "puncRepairKitExist1") # 1 (OK) [cite: 27]
        # (期限・スペア等はスキップ) [cite: 27]
        click_strict(driver, "cleaningKit1") # 1 (OK) [cite: 28]
        # (ジュニアシートはスキップ) [cite: 28]

        # 日常点検完了 (一時保存) [cite: 1]
        click_strict(driver, "a.is-complete")
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 2. 車内清掃 (Interior Cleaning) --- [cite: 29]
        click_strict(driver, "#interiorBtnContainer a")
        click_strict(driver, "interiorDirt1") # 1 (OK) [cite: 30]
        click_strict(driver, "interiorCheckTrouble1") # 1 (OK) [cite: 30]
        click_strict(driver, "soundVolume1") # 1 (OK) [cite: 31]
        click_strict(driver, "lostArticle1") # 1 (なし) [cite: 31]
        click_strict(driver, "a.is-complete") # 完了ボタン [cite: 29]
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 3. 洗車 (Car Wash) --- [cite: 32]
        click_strict(driver, "#washBtnContainer a")
        click_strict(driver, "exteriorDirt2") # 2 (洗車不要) [cite: 33]
        click_strict(driver, "a.is-complete") # 完了ボタン [cite: 32]
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        # --- 4. 外装確認 (Exterior Check) --- [cite: 33]
        click_strict(driver, "#exteriorBtnContainer a")
        click_strict(driver, "exteriorState1") # 1 (OK) [cite: 35]
        click_strict(driver, "a.is-complete") # 完了ボタン [cite: 34]
        WebDriverWait(driver, 5).until(EC.alert_is_present()).accept()

        print("=== SUCCESS: 全工程完了 ===")
    except Exception as e:
        print(f"FATAL ERROR (テスト失敗): {e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
