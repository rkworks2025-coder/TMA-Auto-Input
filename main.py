import sys
import time
import json
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
# TMAログインURL
TMA_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"

# ログインID / PW
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"

# GAS API URL (タイヤデータ取得用)
# ※Safariで不具合があった時のあのURLを使用
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

# ==========================================
# ヘルパー関数
# ==========================================
def get_chrome_driver():
    """ヘッドレスモードでChromeを起動"""
    options = Options()
    options.add_argument('--headless') # 画面なしで動作
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    
    # User-Agentを偽装（bot判定回避のため）
    options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def click_id(driver, eid):
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, eid))).click()
    except:
        print(f"Skip: {eid}")

def set_val(driver, eid, val):
    try:
        el = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, eid)))
        el.clear()
        el.send_keys(str(val))
    except:
        print(f"Skip input: {eid}")

# ==========================================
# メイン処理
# ==========================================
def main():
    # 引数から車両ナンバーを取得 (GASから渡される)
    if len(sys.argv) > 1:
        target_plate = sys.argv[1]
    else:
        print("エラー: 車両ナンバーが指定されていません")
        sys.exit(1)

    print(f"開始: 車両No {target_plate} の自動入力を開始します")
    
    driver = get_chrome_driver()
    
    try:
        # 1. ログイン処理
        print("ログインページへ移動中...")
        driver.get(TMA_LOGIN_URL)
        
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # ログインフォームの入力
            driver.execute_script(f"document.querySelector('input[type=\"text\"]').value = '{TMA_ID}';")
            driver.execute_script(f"document.querySelector('input[type=\"password\"]').value = '{TMA_PW}';")
            
            # ログインボタンクリック
            login_btn = driver.find_element(By.CSS_SELECTOR, "button, input[type='submit']")
            login_btn.click()
            print("ログイン試行...")
            time.sleep(5) # 遷移待機
        except Exception as e:
            print(f"ログイン処理でエラー（または既にログイン済み）: {e}")

        # 2. 車両選択 (リストからtarget_plateを探してクリック)
        print(f"車両 {target_plate} を検索中...")
        try:
            # 画面内のテキストリンクから車両ナンバーを含むものを探す
            xpath = f"//a[contains(text(), '{target_plate}')] | //div[contains(text(), '{target_plate}')]"
            target_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            target_link.click()
            print("車両を選択しました")
            time.sleep(3)
        except Exception as e:
            print("車両選択エラー: リストに見つからないか、既に詳細画面にいる可能性があります")

        # 3. GASからタイヤデータ取得
        tire_data = None
        try:
            res = requests.get(f"{GAS_API_URL}?plate={target_plate}&check=1") # 接続確認も兼ねて
            if res.status_code == 200:
                j = res.json()
                # GASのレスポンス形式に合わせてデータを取得
                # doGetが返すのは { ok:true, std_f:..., prev:{...} } の形
                if j.get("ok"):
                    tire_data = j
                    print("タイヤデータ取得成功")
        except:
            print("タイヤデータ取得失敗")

        # 4. 自動入力実行 (日常点検 -> 車内 -> 洗車 -> 外装 -> 貸出)
        
        # [日常点検]
        print("--- 日常点検 ---")
        click_id(driver, "coolantGauge1") # 冷却水OK
        click_id(driver, "engineOilGauge1") # オイルOK
        click_id(driver, "brakeFluidGauge1") # ブレーキ液OK
        click_id(driver, "washerFluidGauge1") # ★ウォッシャー液 OK[補充] (Value 1)

        # タイヤ入力
        if tire_data:
            click_id(driver, "tireType1")
            
            # 規定値
            set_val(driver, "tireFrontRegularPressure", tire_data.get("std_f", ""))
            set_val(driver, "tireRearRegularPressure", tire_data.get("std_r", ""))
            
            # 測定値 (prevオブジェクトの中にある)
            prev = tire_data.get("prev", {})
            
            wheels = [
                ("rf", "FrontRightCm"), 
                ("lf", "FrontLeftCm"), 
                ("lr", "RearLeftBi4"), 
                ("rr", "RearRightBi4")
            ]
            
            # キーのマッピング (GASのJSONキー -> ループ変数)
            # prevの中身: tread_rf, pre_rf, dot_rf ...
            
            for pre, suf in wheels:
                # 製造週
                week = str(prev.get(f"dot_{pre}", ""))
                if len(week)==3: week = "0"+week
                set_val(driver, f"tireMfr{suf}", week)
                
                # 溝深さ
                depth = str(prev.get(f"tread_{pre}", "0"))
                ip, fp = (depth.split(".") + ["0"])[0:2]
                set_val(driver, f"tireGroove{suf}Ip", ip)
                set_val(driver, f"tireGroove{suf}Fp", fp[0])
                
                # 空気圧
                press = prev.get(f"pre_{pre}", "")
                set_val(driver, f"tirePressure{suf}", press)
                set_val(driver, f"tirePressureAdjusted{suf}", press)
            
            click_id(driver, "tireDamage1")

        # 動作確認・装備・車載品 (一括処理)
        ids_ok = [
            "engineCondition1", "brakeCondition1", "parkingBrakeCondition1", 
            "washerSprayCondition1", "wiperWipeCondition1",
            "inspectionCertificateExist1", "inspectionStickerExist1", "autoLiabilityExist1",
            "maintenanceStickerExist1", "roomStickerExist1", "deodorantsExist1",
            "backMonitor1", "cornerSensor1", "brakeSupport1", "laneDevianceAlert1", "driveRecorder1",
            "turnSignal1", "fuelCap1", "carStickerExist1",
            "warningTrianglePlateDamage1", "puncRepairKitExist1", "cleaningKit1"
        ]
        for i in ids_ok: click_id(driver, i)
        
        # 完了ボタン (Daily)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('daily');")
        time.sleep(2)

        # [車内清掃]
        print("--- 車内清掃 ---")
        click_id(driver, "interiorDirt01")
        click_id(driver, "interiorCheckTrouble01")
        click_id(driver, "soundVolume01")
        click_id(driver, "lostArticle01")
        driver.execute_script("if(typeof completeTask === 'function') completeTask('interior');")
        time.sleep(2)

        # [洗車]
        print("--- 洗車 ---")
        click_id(driver, "exteriorDirt02") # 洗車不要 (Value 2)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('wash');")
        time.sleep(2)

        # [外装確認]
        print("--- 外装確認 ---")
        click_id(driver, "exteriorState01")
        driver.execute_script("if(typeof completeTask === 'function') completeTask('exterior');")
        time.sleep(2)

        # [貸出準備]
        print("--- 貸出準備 ---")
        # 走行距離ダミー
        try:
             driver.find_element(By.CSS_SELECTOR, "input.input-bg-pink").send_keys("10000")
        except: pass
        
        # ラジオボタン系 (name属性で操作)
        js_radios = [
            "document.getElementsByName('refuel')[1].checked = true;", # 給油:未実施
            "document.getElementsByName('fuel_card')[0].checked = true;", # カード:OK
            "document.getElementsByName('room_seal')[0].checked = true;", # シール:OK
            "document.getElementsByName('park_check')[0].checked = true;" # 駐車:OK
        ]
        for js in js_radios:
            try: driver.execute_script(js)
            except: pass
            
        driver.execute_script("if(typeof completeTask === 'function') completeTask('lend');")
        time.sleep(2)

        # 最終完了
        print("全工程完了")
        try:
            driver.find_element(By.CSS_SELECTOR, "a.is-complete").click()
            WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
        except: pass

    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
