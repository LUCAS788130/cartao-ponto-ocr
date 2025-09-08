import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime, timedelta
import pytesseract
from PIL import Image
import io

st.set_page_config(page_title="CARTÃO DE PONTO ➜ CSV")
st.markdown("<h1 style='text-align: center;'>🕒 CONVERSOR UNIVERSAL DE CARTÃO DE PONTO</h1>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("📎 Envie o cartão de ponto em PDF ou imagem", type=["pdf","png","jpg","jpeg"])

# ---------------------------
# Função de OCR para PDFs escaneados ou imagens
# ---------------------------
def extrair_texto_ocr(file):
    if file.type == "application/pdf":
        texto_total = ""
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                imagem = page.to_image(resolution=300).original
                texto_total += pytesseract.image_to_string(imagem, lang='por') + "\n"
        return texto_total
    else:  # imagem direta
        imagem = Image.open(file)
        return pytesseract.image_to_string(imagem, lang='por')

# ---------------------------
# Função de detecção de layout
# ---------------------------
def detectar_layout(texto):
    linhas = texto.split("\n")
    for linha in linhas:
        if re.search(r"\d{2}/\d{2}/\d{4}", linha):
            partes = linha.split()
            if len(partes) >= 5 and any(o in linha.upper() for o in ["FERIADO", "D.S.R", "INTEGRAÇÃO", "FALTA", "LICENÇA REMUNERADA - D"]):
                return "novo"
    return "antigo"

# ---------------------------
# Função de processamento layout antigo
# ---------------------------
def processar_layout_antigo(texto):
    linhas = [linha.strip() for linha in texto.split("\n") if linha.strip()]
    registros = {}
    def eh_horario(p): return ":" in p and len(p) == 5 and p.replace(":", "").isdigit()

    for ln in linhas:
        partes = ln.split()
        if len(partes) >= 2 and "/" in partes[0]:
            try:
                data = datetime.strptime(partes[0], "%d/%m/%Y").date()
                pos_dia = partes[2:]
                tem_ocorrencia = any(not eh_horario(p) for p in pos_dia)
                horarios = [p for p in pos_dia if eh_horario(p)]
                registros[data] = [] if tem_ocorrencia else horarios
            except: pass

    if registros:
        inicio = min(registros.keys())
        fim = max(registros.keys())
        dias_corridos = [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
        tabela = []
        for dia in dias_corridos:
            linha = {"Data": dia.strftime("%d/%m/%Y")}
            horarios = registros.get(dia, [])
            for i in range(2):
                entrada = horarios[i*2] if len(horarios) > i*2 else ""
                saida = horarios[i*2+1] if len(horarios) > i*2+1 else ""
                linha[f"Entrada{i+1}"] = entrada
                linha[f"Saída{i+1}"] = saida
            tabela.append(linha)
        return pd.DataFrame(tabela)
    return pd.DataFrame()

# ---------------------------
# Função de processamento layout novo / universal
# ---------------------------
def processar_layout_novo(texto):
    linhas = texto.split("\n")
    registros = []

    ocorrencias_que_zeram = [
        "D.S.R","FERIADO","FÉRIAS","FALTA","ATESTADO","FERIAS","DISPENSA",
        "INTEGRAÇÃO","LICENÇA REMUNERADA","SUSPENSÃO","DESLIGAMENTO",
        "COMPENSA DIA","FOLGA COMPENSATÓRIA","ATESTADO MÉDICO"
    ]

    for linha in linhas:
        match = re.search(r"(\d{2}/\d{2}/\d{4})", linha)
        if match:
            data_str = match.group(1)
            linha_upper = linha.upper()
            # Exceção para DISPENSA FALTA DE PRODUÇÃO - P
            if any(oc in linha_upper for oc in ocorrencias_que_zeram) and \
               "SAÍDA ANTECIPADA" not in linha_upper and \
               "ATRASO" not in linha_upper and \
               "DISPENSA FALTA DE PRODUÇÃO - P" not in linha_upper:
                registros.append((data_str, []))
                continue
            # Extrair apenas a parte de marcações
            corte_ocorrencias = r"\s+(HORA|D\.S\.R|FALTA|FERIADO|FÉRIAS|ATESTADO|DISPENSA|SAÍDA ANTECIPADA|INTEGRAÇÃO|SUSPENSÃO|DESLIGAMENTO|FOLGA|COMPENSA|ATRASO)"
            parte_marcacoes = re.split(corte_ocorrencias, linha_upper)[0]
            horarios = re.findall(r"\d{2}:\d{2}[a-z]?", parte_marcacoes)
            horarios = [h[:-1] if h[-1].isalpha() else h for h in horarios]
            horarios = [h for h in horarios if re.match(r"\d{2}:\d{2}", h)]
            if len(horarios)%2 !=0: horarios = horarios[:-1]
            horarios = horarios[:12]  # 6 pares no máximo
            registros.append((data_str, horarios))

    if not registros: return pd.DataFrame()
    df = pd.DataFrame(registros, columns=["Data","Horários"])
    df["Data"] = pd.to_datetime(df["Data"], dayfirst=True)
    data_inicio = df["Data"].min()
    data_fim = df["Data"].max()
    todas_datas = [(data_inicio + timedelta(days=i)).strftime("%d/%m/%Y") for i in range((data_fim - data_inicio).days+1)]
    registros_dict = {d.strftime("%d/%m/%Y"):h for d,h in zip(df["Data"],df["Horários"])}

    estrutura = {"Data":[]}
    for i in range(1,7):
        estrutura[f"Entrada{i}"]=[]
        estrutura[f"Saída{i}"]=[]
    for data in todas_datas:
        estrutura["Data"].append(data)
        horarios = registros_dict.get(data, [])
        pares = horarios + [""]*(12-len(horarios))
        for i in range(6):
            estrutura[f"Entrada{i+1}"].append(pares[2*i])
            estrutura[f"Saída{i+1}"].append(pares[2*i+1])
    return pd.DataFrame(estrutura)

# ---------------------------
# Fluxo principal
# ---------------------------
if uploaded_file:
    with st.spinner("⏳ Processando..."):
        # Extrair texto: OCR se necessário
        try:
            texto = ""
            if uploaded_file.type == "application/pdf":
                with pdfplumber.open(uploaded_file) as pdf:
                    # Tenta extrair texto normal
                    for page in pdf.pages:
                        texto += page.extract_text() or ""
                if not texto.strip():  # sem texto, aplicar OCR
                    texto = extrair_texto_ocr(uploaded_file)
            else:
                texto = extrair_texto_ocr(uploaded_file)
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")
            texto = ""

        if texto.strip():
            layout = detectar_layout(texto)
            st.info(f"📄 Layout detectado: **{layout.upper()}**")
            if layout == "novo":
                df = processar_layout_novo(texto)
            else:
                df = processar_layout_antigo(texto)

            if not df.empty:
                st.success("✅ Conversão concluída com sucesso!")
                st.dataframe(df, use_container_width=True)
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Baixar CSV", data=csv, file_name="cartao_convertido.csv", mime="text/csv")
            else:
                st.warning("❌ Não foi possível extrair os dados do cartão.")
        else:
            st.warning("❌ Nenhum texto detectado no arquivo.")

st.markdown("""
<hr>
<p style='text-align: center; font-size: 13px;'>
🔒 Este site está em conformidade com a <strong>Lei Geral de Proteção de Dados (LGPD)</strong>.<br>
Os arquivos enviados são utilizados apenas para conversão e não são armazenados nem compartilhados.<br>
👨‍💻 Desenvolvido por <strong>Lucas de Matos Coelho</strong>
</p>
""", unsafe_allow_html=True)
