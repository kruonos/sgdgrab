from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, SessionNotCreatedException
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path
import time, os
import requests

# ===== Config =====
PROFILE_DIR  = r"C:\Users\gilbe\sgd_selenium_profile"   # perfil LIMPO só do Selenium
TARGET       = "https://sgd.correios.com.br/sgd/app/"
DOWNLOAD_DIR = Path("downloads")

os.makedirs(PROFILE_DIR, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Limpa travas se sobrou algo do último crash
for f in ["SingletonLock", "SingletonCookie", "SingletonSocket", "SingletonSemaphore"]:
    p = Path(PROFILE_DIR, f)
    if p.exists():
        try: p.unlink()
        except Exception as e:
            print(f"Failed to remove {p}: {e}")

# ===== Browser =====
options = webdriver.ChromeOptions()
options.add_argument(fr"--user-data-dir={PROFILE_DIR}")
options.add_argument("--no-first-run")
options.add_argument("--no-default-browser-check")
options.add_argument("--disable-backgrounding-occluded-windows")
options.add_argument("--disable-features=Translate,MediaRouter")
options.add_argument("--disable-popup-blocking")

service = Service(ChromeDriverManager().install())
try:
    driver = webdriver.Chrome(service=service, options=options)
except SessionNotCreatedException:
    print("[ERRO] Falha ao iniciar o Chrome. Feche o Chrome, use perfil dedicado e atualize o navegador.")
    raise

wait = WebDriverWait(driver, 25)

# ===== Acessa & Login =====
driver.get(TARGET)
try:
    wait.until(EC.url_contains("sgd.correios.com.br"))
except TimeoutException:
    driver.execute_script("window.location.href = arguments[0];", TARGET)
    wait.until(EC.url_contains("sgd.correios.com.br"))

wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "entrar"))).click()
driver.find_element(By.ID, "username").send_keys("gpp159753.")
pwd = driver.find_element(By.ID, "password")
pwd.send_keys("C159@753")
pwd.send_keys(Keys.RETURN)

# ===== Menu -> Consulta Objetos =====
wait.until(EC.element_to_be_clickable((By.ID, "nav-menu"))).click()
wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "expandir"))).click()
wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Consulta Objetos"))).click()
wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "opcoes"))).click()
wait.until(EC.element_to_be_clickable((By.ID, "chkConsultarVariosObjetos"))).click()

# ===== Entrada dos códigos via terminal =====
print("Paste up to 200 codes (space or newline separated).")
print("Press ENTER on an empty line to finish.\n")

codes = []
while True:
    line = input()
    if not line: break
    codes.extend(line.split())
    if len(codes) >= 200: break

codes = codes[:200]
print(f"\nYou entered {len(codes)} codes.")
codes_text = "\n".join(codes)

# ===== Preenche campo e pesquisa =====
campo_codigos = wait.until(EC.presence_of_element_located((By.ID, "txtAreaObjetos")))
campo_codigos.clear()
campo_codigos.send_keys(codes_text)
wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Pesquisar"))).click()
  
def open_and_quick_save_all_ars():
    saved, skipped = 0, 0
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table, div.resultados, div.tabela")))
    except TimeoutException:
        pass

    anchors = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.verArDigital")))
    for a in anchors:
        style = (a.get_attribute("style") or "").replace(" ", "").lower()
        onclick = a.get_attribute("onclick") or ""
        if "opacity:0.2" in style or "verArDigital" not in onclick:
            skipped += 1
            continue

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
        time.sleep(0.1)

        before_handles = set(driver.window_handles)
        try:
            try:
                a.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", a)
        except Exception:
            driver.execute_script("arguments[0].click();", a)

        # wait new tab
        try:
            wait.until(lambda d: len(set(d.window_handles) - before_handles) == 1)
        except TimeoutException:
            skipped += 1
            continue

        new_handle = (set(driver.window_handles) - before_handles).pop()
        main_handle = driver.current_window_handle

        try:
            driver.switch_to.window(new_handle)
            time.sleep(0.8)  # let image load
            try:
                src = driver.find_element(By.TAG_NAME, "img").get_attribute("src")
                response = requests.get(src)
                if response.ok:
                    ext = Path(src.split("?")[0]).suffix or ".png"
                    filename = f"ar_{int(time.time()*1000)}{ext}"
                    path = DOWNLOAD_DIR / filename
                    with open(path, "wb") as f:
                        f.write(response.content)
                    saved += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        finally:
            try:
                driver.close()
            except:
                pass
            driver.switch_to.window(main_handle)
            time.sleep(0.2)
    print(f"Saved: {saved}  |  Skipped: {skipped}")

# ===== Run =====
import traceback

try:
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.verArDigital")))
    open_and_quick_save_all_ars()
except Exception as e:
    print(f"[ERROR] {e}")
    traceback.print_exc()

time.sleep(1)
driver.quit()
