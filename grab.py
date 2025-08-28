# sgd_ar_playwright.py
# Requisitos:
#   pip install playwright
#   python -m playwright install
#
# Uso:
#   python sgd_ar_playwright.py
#
# Observações:
# - HEADLESS=False para depurar (visualizar o navegador). Após estabilizar, pode usar True.
# - O script tenta:
#     1) Detectar/abrir tela de login (inclusive dentro de iframes).
#     2) Preencher usuário/senha e submeter.
#     3) Abrir "Pesquisar Objeto" -> "Consultar vários objetos".
#     4) Colar a lista de códigos, pesquisar.
#     5) Para cada código, clicar no "Ver AR Digital" e salvar o PDF.
# - Se algum passo falhar, são gerados HTML/PNG de depuração em downloads_ar_sgd/.

import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError, Page, Frame, Response

LOGIN_URL = "https://sgd.correios.com.br/sgd/app/"  # solicitado por você
# ⚠️ O ponto faz parte do usuário
USERNAME = os.getenv("SGD_USER", "gpp159753.")
PASSWORD = os.getenv("SGD_PASS", "C159@753")

CODES = [
    "YA259824691BR",
    "YA259825184BR",
    "YA259823912BR",
    "YA259826984BR",
    "YA259825900BR",
    "YA259822421BR",
    "YA259822072BR",
    "YA259821094BR",
]

DOWNLOAD_DIR = Path.cwd() / "downloads_ar_sgd"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

HEADLESS = False
TIMEOUT_MS = 30000  # 30s por espera

def dump_debug(page_or_frame, name: str):
    """Salva HTML e PNG do contexto atual para depuração."""
    try:
        page = page_or_frame.page if hasattr(page_or_frame, "page") else page_or_frame
        html_path = DOWNLOAD_DIR / f"{name}.html"
        png_path = DOWNLOAD_DIR / f"{name}.png"
        html = page.content()
        with open(html_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(html)
        page.screenshot(path=str(png_path), full_page=True)
        print(f"[DEBUG] URL: {page.url}")
        print(f"[DEBUG] Salvos: {html_path} e {png_path}")
    except Exception as e:
        print(f"[DEBUG] Falha ao salvar debug {name}: {e}")

def all_frames(page: Page) -> List[Frame]:
    """Retorna a lista de frames (inclui o frame principal)."""
    return [page.main_frame] + page.frames

def find_first_locator(page: Page, selectors: List[str], timeout_ms: int = TIMEOUT_MS) -> Optional[Tuple[Frame, str]]:
    """
    Procura o primeiro seletor que exista/esteja visível em QUALQUER frame.
    Retorna (frame, seletor_encontrado) ou None.
    """
    for sel in selectors:
        for fr in all_frames(page):
            try:
                loc = fr.locator(sel).first
                loc.wait_for(state="visible", timeout=timeout_ms)
                return fr, sel
            except PWTimeoutError:
                continue
            except Exception:
                continue
    return None

def click_first(page: Page, selectors: List[str], timeout_ms: int = TIMEOUT_MS) -> bool:
    """Clica no primeiro seletor disponível em qualquer frame."""
    found = find_first_locator(page, selectors, timeout_ms=timeout_ms)
    if not found:
        return False
    fr, sel = found
    try:
        fr.locator(sel).first.click(timeout=timeout_ms)
        return True
    except Exception:
        return False

def fill_first(page: Page, selectors: List[str], text: str, timeout_ms: int = TIMEOUT_MS) -> bool:
    """Preenche o primeiro campo encontrado com o texto."""
    found = find_first_locator(page, selectors, timeout_ms=timeout_ms)
    if not found:
        return False
    fr, sel = found
    try:
        fr.locator(sel).first.fill(text, timeout=timeout_ms)
        return True
    except Exception:
        return False

def try_call_opcoes(page: Page):
    """Tenta executar a função JS opcoes() em todos os frames (abre o menu 'Pesquisar Objeto')."""
    for fr in all_frames(page):
        try:
            fr.evaluate("()=>{ if (typeof opcoes === 'function') opcoes(); }")
            time.sleep(0.3)
        except Exception:
            pass

def login(page: Page):
    print("[INFO] Acessando URL de login…")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

    # Algumas instâncias mostram um botão 'Acessar/Entrar/Login' antes do formulário
    print("[INFO] Verificando front-door de acesso…")
    click_first(page, [
        "xpath=//a[contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'acessar') or contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'entrar') or contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'login')]",
        "xpath=//button[contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'acessar') or contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'entrar') or contains(translate(.,'ACESSARENTARLOGIN','acessarentarlogin'),'login')]",
    ], timeout_ms=6000)

    # Campos de usuário/senha (busca ampla por id/name/type)
    print("[INFO] Procurando campos de usuário/senha…")
    ok_user = fill_first(page, [
        "input#username",
        "input[name='username']",
        "input[type='email']",
        "input[type='text']",
    ], USERNAME, timeout_ms=10000)

    ok_pass = fill_first(page, [
        "input#password",
        "input[name='password']",
        "input[type='password']",
    ], PASSWORD, timeout_ms=10000)

    if not ok_user or not ok_pass:
        dump_debug(page, "login_campos_nao_encontrados")
        raise RuntimeError("Campos de login não localizados (nem em iframes).")

    # Botão de submit
    print("[INFO] Enviando credenciais…")
    if not click_first(page, [
        "button[type='submit']",
        "input[type='submit']",
        "xpath=//button[contains(translate(.,'ENTRARLOGIN','entrarlogin'),'entrar') or contains(translate(.,'ENTRARLOGIN','entrarlogin'),'login')]",
    ], timeout_ms=8000):
        # Fallback: Enter no campo de senha
        found = find_first_locator(page, [
            "input#password",
            "input[name='password']",
            "input[type='password']",
        ], timeout_ms=3000)
        if not found:
            dump_debug(page, "login_sem_submit")
            raise RuntimeError("Não foi possível submeter o formulário de login.")
        fr, sel = found
        fr.locator(sel).press("Enter")

    # Espera voltar para app SGD (pode haver redirecionamentos)
    print("[INFO] Aguardando pós-login…")
    try:
        page.wait_for_url(re.compile(r"sgd.*"), timeout=TIMEOUT_MS)
    except PWTimeoutError:
        dump_debug(page, "login_timeout_pos")
        raise RuntimeError("Não houve redirecionamento esperado para o SGD após login.")

def open_consultar_varios_objetos(page: Page) -> Page:
    print("[INFO] Abrindo menu 'Pesquisar Objeto'…")
    try_call_opcoes(page)

    if not click_first(page, [
        "a[title='Pesquisar Objeto']",
        "a.opcoes",
        "xpath=//a[contains(@onclick,'opcoes()')]",
        "xpath=//button[contains(translate(.,'PESQUISAROBJETO','pesquisarobjeto'),'pesquisar objeto')]",
        "xpath=//a[.//i[contains(@class,'opcoes') or contains(@class,'fa-search')]]",
    ], timeout_ms=8000):
        dump_debug(page, "menu_pesquisar_nao_encontrado")
        raise RuntimeError("Menu 'Pesquisar Objeto' não localizado.")

    print("[INFO] Selecionando 'Consultar vários objetos'…")
    found = find_first_locator(page, [
        "xpath=//a[contains(translate(.,'ÁÀÃÂÉÈÊÍÌÎÓÒÔÕÚÙÛÇVARIOS','aaaaeeeiiioooouuucvarios'),'consultar varios objetos')]",
        "xpath=//button[contains(translate(.,'ÁÀÃÂÉÈÊÍÌÎÓÒÔÕÚÙÛÇVARIOS','aaaaeeeiiioooouuucvarios'),'consultar varios objetos')]",
        "xpath=//a[contains(.,'Consultar Vários Objetos')]",
        "xpath=//a[contains(.,'Consultar vários objetos')]",
        "xpath=//*[self::a or self::span or self::button][contains(.,'Consultar')][contains(.,'objet')]",
    ], timeout_ms=8000)
    if not found:
        dump_debug(page, "consultar_varios_nao_encontrado")
        raise RuntimeError("Link 'Consultar vários objetos' não localizado.")

    fr, sel = found
    with page.context.expect_page() as new_page_info:
        fr.locator(sel).first.click(timeout=TIMEOUT_MS)
    new_page = new_page_info.value

    try:
        new_page.wait_for_load_state("load", timeout=TIMEOUT_MS)
    except PWTimeoutError:
        pass

    return new_page

def pesquisar_codigos(page: Page, codes: List[str]):
    print("[INFO] Localizando área de texto para múltiplos objetos…")
    ta_found = find_first_locator(page, [
        "xpath=//textarea[contains(@id,'obj') or contains(@name,'obj') or contains(@placeholder,'objet')]",
        "textarea",
    ], timeout_ms=10000)
    if not ta_found:
        dump_debug(page, "textarea_nao_encontrada")
        raise RuntimeError("Textarea de múltiplos objetos não encontrada.")
    fr, sel = ta_found
    fr.locator(sel).fill("\n".join(codes))

    print("[INFO] Acionando 'Pesquisar'…")
    if not click_first(page, [
        "xpath=//button[contains(translate(.,'PESQUISARBUSCAR','pesquisarbuscar'),'pesquisar')]",
        "xpath=//button[contains(translate(.,'PESQUISARBUSCAR','pesquisarbuscar'),'buscar')]",
        "xpath=//a[contains(@class,'btn') and (contains(.,'Pesquisar') or contains(.,'Buscar'))]",
        "xpath=//input[@type='submit' and (contains(@value,'Pesquisar') or contains(@value,'Buscar'))]",
    ], timeout_ms=8000):
        dump_debug(page, "botao_pesquisar_nao_encontrado")
        raise RuntimeError("Botão 'Pesquisar' não encontrado.")

    print("[INFO] Aguardando a tabela de resultados…")
    found = find_first_locator(page, [
        "xpath=//table[contains(@class,'table')]",
        "xpath=//div[contains(@class,'result') or contains(@id,'result')]//table",
        "xpath=//*[self::table or self::div][contains(@class,'resultado') or contains(@id,'resultado')]//table",
    ], timeout_ms=15000)
    if not found:
        dump_debug(page, "tabela_resultados_nao_apareceu")
        raise RuntimeError("Tabela de resultados não apareceu após a pesquisa.")

def wait_and_save_pdf(response_bucket: List[Response], code: str, timeout_ms: int = 20000) -> bool:
    """Espera por uma resposta PDF recente e salva como <code>.pdf."""
    # Polling simples do balde de respostas recentes
    deadline = time.time() + timeout_ms / 1000.0
    last_seen_len = len(response_bucket)
    while time.time() < deadline:
        # Verifica se houve novas respostas
        if len(response_bucket) > last_seen_len:
            for resp in response_bucket[last_seen_len:]:
                try:
                    ctype = (resp.headers or {}).get("content-type", "")
                except Exception:
                    ctype = ""
                if "application/pdf" in ctype.lower():
                    try:
                        content = resp.body()
                        out_path = DOWNLOAD_DIR / f"{code}.pdf"
                        with open(out_path, "wb") as f:
                            f.write(content)
                        return True
                    except Exception:
                        pass
            last_seen_len = len(response_bucket)
        time.sleep(0.25)
    return False

def baixar_ars(page: Page, codes: List[str]):
    """
    Para cada código:
      - Procura um link com onclick="verArDigital('CODE')"
      - Clica e captura o PDF via interceptação de resposta
      - Salva em downloads_ar_sgd/<CODE>.pdf
    """
    print("[INFO] Iniciando downloads dos ARs…")
    # Balde para armazenar respostas (anexado ao contexto)
    response_bucket: List[Response] = []

    def on_response(resp: Response):
        # Guarda respostas potencialmente úteis
        try:
            # só guardamos se suspeita de PDF para reduzir memória
            ctype = (resp.headers or {}).get("content-type", "")
            if "application/pdf" in ctype.lower():
                response_bucket.append(resp)
        except Exception:
            pass

    page.context.on("response", on_response)

    baixados = []
    ausentes = []

    for code in codes:
        print(f"[INFO] Código {code}: procurando link de AR Digital…")

        # Seletor estrito no onclick do link
        sel_strict = f"xpath=//a[contains(@class,'verArDigital') and contains(@onclick,\"verArDigital('{code}'\")]"
        found = find_first_locator(page, [sel_strict], timeout_ms=6000)

        if not found:
            # fallback: buscar todos e filtrar atributo onclick no lado do cliente
            sel_loose = "xpath=//a[contains(@class,'verArDigital') and contains(@onclick,'verArDigital')]"
            found = find_first_locator(page, [sel_loose], timeout_ms=4000)
            if found:
                fr, sel = found
                # Filtra pelo atributo
                elems = fr.locator(sel)
                count = elems.count()
                link_idx = None
                for i in range(count):
                    onclick = elems.nth(i).get_attribute("onclick") or ""
                    if code in onclick:
                        link_idx = i
                        break
                if link_idx is not None:
                    link = elems.nth(link_idx)
                else:
                    link = None
            else:
                link = None
        else:
            fr, sel = found
            link = fr.locator(sel).first

        if not link:
            print(f"[WARN] {code}: AR Digital não encontrado na listagem.")
            ausentes.append(code)
            continue

        # Antes de clicar, limpa o balde de respostas para detectar o PDF correto
        response_bucket.clear()

        # Tenta clicar e capturar um PDF
        try:
            with page.expect_download(timeout=5000) as download_info:
                link.click()
            # Se o servidor for download direto, Playwright captura aqui:
            dl = download_info.value
            out_path = DOWNLOAD_DIR / f"{code}.pdf"
            dl.save_as(str(out_path))
            print(f"[OK] {code}: PDF salvo (download direto).")
            baixados.append(code)
            continue
        except Exception:
            # Se abrir em nova aba/visualizador, tentamos via resposta PDF
            try:
                link.click(timeout=5000)
            except Exception:
                pass

        # Pequena espera para rede disparar
        ok = wait_and_save_pdf(response_bucket, code, timeout_ms=20000)
        if ok:
            print(f"[OK] {code}: PDF salvo (capturado via rede).")
            baixados.append(code)
        else:
            print(f"[WARN] {code}: não foi possível capturar o PDF.")
            ausentes.append(code)

        # Fecha popups, se houver
        if len(page.context.pages) > 1:
            for p in page.context.pages[1:]:
                try:
                    p.close()
                except Exception:
                    pass

    # Resumo
    print("\n== AR Digital baixado para ==", DOWNLOAD_DIR)
    for c in baixados:
        print("  ✓", c)
    if ausentes:
        print("\n== Sem AR Digital disponível / não baixado ==")
        for c in ausentes:
            print("  -", c)

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            login(page)
            # Segurança adicional: aguarda estabilizar em URL do SGD
            try:
                page.wait_for_url(re.compile(r"sgd"), timeout=TIMEOUT_MS)
            except PWTimeoutError:
                pass

            page = open_consultar_varios_objetos(page)
            pesquisar_codigos(page, CODES)
            baixar_ars(page, CODES)

        except Exception as e:
            print(f"[ERRO] {e}")
            dump_debug(page, "falha_geral")
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()
