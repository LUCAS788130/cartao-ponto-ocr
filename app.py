import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime, timedelta

# --------------------------
# Configuração inicial
# --------------------------
st.set_page_config(page_title="CARTÃO DE PONTO ➜ CSV", layout="wide")

# CSS customizado
st.markdown("""
    <style>
        body {
            background: linear-gradient(120deg, #1f1c2c, #928dab);
            color: #f5f5f5;
        }
        .main {
            background: rgba(0, 0, 0, 0.15);
            border-radius: 15px;
            padding: 20px;
        }
        h1 {
            font-size: 40px !important;
            color: #ffffff !important;
            text-align: center;
            margin-bottom: 20px;
        }
        .stButton>button {
            background: #4CAF50;
            color: white;
            border-radius: 10px;
            padding: 0.6em 1.2em;
            font-weight: bold;
            transition: 0.3s;
        }
        .stButton>button:hover {
            background: #45a049;
            transform: scale(1.05);
        }
        .stDownloadButton>button {
            background: #1976D2;
            color: white;
            border-radius: 10px;
            padding: 0.6em 1.2em;
            font-weight: bold;
        }
        .stDownloadButton>button:hover {
            background: #0D47A1;
            transform: scale(1.05);
        }
        .footer {
            text-align: center;
            font-size: 13px;
            color: #ddd;
            margin-top: 50px;
        }
    </style>
""", unsafe_allow_html=True)

# --------------------------
# Título
# --------------------------
st.markdown("<h1>🕒 Conversor Inteligente de Cartão de Ponto</h1>", unsafe_allow_html=True)

# --------------------------
# Upload do PDF
# --------------------------
uploaded_file = st.file_uploader("📎 Envie o cartão de ponto em PDF", type="pdf")

# --------------------------
# Detectar layout
# --------------------------
def detectar_layout(texto):
    if "SISTEMA DE PONTO ELETRONICO" in texto and "CAIXA - SIPON" in texto:
        return "caixa"
    linhas = texto.split("\n")
    for linha in linhas:
        if re.match(r"\d{2}/\d{2}/\d{4}", linha):
            partes = linha.split()
            if len(partes) >= 5 and any(o in linha.upper() for o in ["FERIADO", "D.S.R", "INTEGRAÇÃO", "FALTA", "LICENÇA REMUNERADA - D"]):
                return "novo"
    return "antigo"

# --------------------------
# Layout antigo
# --------------------------
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

# --------------------------
# Layout novo
# --------------------------
def processar_layout_novo(texto):
    linhas = texto.split("\n")
    registros = []
    ocorrencias_que_zeram = [
        "D.S.R","FERIADO","FÉRIAS","FALTA","ATESTADO","FERIAS","DISPENSA",
        "INTEGRAÇÃO","LICENÇA REMUNERADA","SUSPENSÃO","DESLIGAMENTO",
        "COMPENSA DIA","FOLGA COMPENSATÓRIA","ATESTADO MÉDICO"
    ]
    for linha in linhas:
        match = re.match(r"(\d{2}/\d{2}/\d{4})", linha)
        if match:
            data_str = match.group(1)
            linha_upper = linha.upper()
            if any(oc in linha_upper for oc in ocorrencias_que_zeram) and \
               "SAÍDA ANTECIPADA" not in linha_upper and \
               "ATRASO" not in linha_upper and \
               "DISPENSA FALTA DE PRODUÇÃO - P" not in linha_upper:
                registros.append((data_str, []))
                continue
            corte_ocorrencias = r"\s+(HORA|D\.S\.R|FALTA|FERIADO|FÉRIAS|ATESTADO|DISPENSA|SAÍDA ANTECIPADA|INTEGRAÇÃO|SUSPENSÃO|DESLIGAMENTO|FOLGA|COMPENSA|ATRASO)"
            parte_marcacoes = re.split(corte_ocorrencias, linha_upper)[0]
            horarios = re.findall(r"\d{2}:\d{2}[a-z]?", parte_marcacoes)
            horarios = [h[:-1] if h[-1].isalpha() else h for h in horarios]
            horarios = [h for h in horarios if re.match(r"\d{2}:\d{2}", h)]
            if len(horarios) % 2 != 0:
                horarios = horarios[:-1]
            horarios = horarios[:12]
            registros.append((data_str, horarios))
    if not registros: return pd.DataFrame()
    df = pd.DataFrame(registros, columns=["Data","Horários"])
    df["Data"] = pd.to_datetime(df["Data"], dayfirst=True)
    data_inicio = df["Data"].min()
    data_fim = df["Data"].max()
    todas_datas = [(data_inicio + timedelta(days=i)).strftime("%d/%m/%Y") for i in range((data_fim - data_inicio).days+1)]
    registros_dict = {d.strftime("%d/%m/%Y"):h for d,h in zip(df["Data"],df["Horários"])}
    estrutura = {"Data":[]}
    for i in range(1,7): estrutura[f"Entrada{i}"]=[]; estrutura[f"Saída{i}"]=[] 
    for data in todas_datas:
        estrutura["Data"].append(data)
        horarios = registros_dict.get(data, [])
        pares = horarios + [""]*(12-len(horarios))
        for i in range(6):
            estrutura[f"Entrada{i+1}"].append(pares[2*i])
            estrutura[f"Saída{i+1}"].append(pares[2*i+1])
    return pd.DataFrame(estrutura)

# --------------------------
# Layout CAIXA - SIPON (corrigido e robusto)
# --------------------------
def processar_layout_caixa(texto_pdf):
    registros_dict = {}

    paginas = texto_pdf.split("\f")
    for page_text in paginas:
        linhas = page_text.split("\n")
        mes_ano = re.search(r"Mes/Ano\s*:\s*(\d+)\s*/\s*(\d+)", page_text)
        mes, ano = (int(mes_ano.group(1)), int(mes_ano.group(2))) if mes_ano else (1, 2000)

        dia_atual = None
        horarios_dia = []

        for linha in linhas:
            linha_strip = linha.strip()
            linha_upper = linha_strip.upper()

            if "QTDE" in linha_upper or "QUANTIDADE" in linha_upper:
                continue

            match = re.match(r"(\d{1,2})\s*-\s*[A-Z]{3}", linha_strip)
            if match:
                # salva dia anterior
                if dia_atual and len(horarios_dia) >= 2:
                    pares_validos = []
                    for i in range(0, len(horarios_dia), 2):
                        if i+1 < len(horarios_dia):
                            pares_validos.append(horarios_dia[i:i+2])
                    if dia_atual in registros_dict:
                        registros_dict[dia_atual].extend(pares_validos)
                    else:
                        registros_dict[dia_atual] = pares_validos

                dia = int(match.group(1))
                dia_atual = f"{dia:02d}/{mes:02d}/{ano}"
                horarios_dia = []

                if any(oc in linha_upper for oc in ["FERIADO","FALTA","ABN/DEC.CHEFIA","LICENÇA","D.S.R"]):
                    registros_dict[dia_atual] = []
                    dia_atual = None
                    continue

                horarios = re.findall(r"\d{2}:\d{2}", linha_strip)
                if horarios:
                    horarios = horarios[1:]  # ignora jornada
                    horarios_dia.extend(horarios)
            else:
                if
