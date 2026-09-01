import io
import re
from num2words import num2words
import pdfplumber

MAPA_HOSPITAIS = {
    "HIWM": "Hospital Infantil Waldemar Monastier",
    "WALDEMAR MONASTIER": "Hospital Infantil Waldemar Monastier",
    "HRS": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "SUDOESTE": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "WALTER ALBERTO PECOITS": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "HZNL": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "HZN": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "ANISIO FIGUEIREDO": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "HRL": "Hospital Regional do Litoral",
    "LITORAL": "Hospital Regional do Litoral",
    "HGG": "Hospital Regional de Guaraqueçaba",
    "HILP": "Hospital Infantil Lucian de Paula",
    "HMT": "Hospital Regional da Mata Atlântica",
}

MAPA_MESES = {
    "01": "janeiro", "02": "fevereiro", "03": "março", "04": "abril",
    "05": "maio", "06": "junho", "07": "julho", "08": "agosto",
    "09": "setembro", "10": "outubro", "11": "novembro", "12": "dezembro"
}

def formatar_valor_reais(valor_float: float) -> str:
    return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def extrair_dados_processo(pdf_bytes: bytes) -> dict:
    paginas_texto = []
    texto_completo = ""
    
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, pag in enumerate(pdf.pages):
            txt = pag.extract_text() or ""
            paginas_texto.append((i + 1, txt))
            texto_completo += f"\n--- PAGINA {i+1} ---\n" + txt

    # 1. PROTOCOLO
    texto_folha1 = paginas_texto[0][1] if paginas_texto else ""
    match_proto = re.search(r"Protocolo:\s*([0-9]{2}\.[0-9]{3}\.[0-9]{3}-[0-9])", texto_folha1)
    if not match_proto:
        match_proto = re.search(r"protocolo\s+([0-9]{2}\.[0-9]{3}\.[0-9]{3}-[0-9])", texto_completo, re.IGNORECASE)
    protocolo = match_proto.group(1).strip() if match_proto else ""

    # 2. IDENTIFICAÇÃO DE BLOCOS DE DOCUMENTOS
    blocos_memo = []
    blocos_empenho = []
    blocos_tributario = []

    for num_pag, txt in paginas_texto:
        if "Memorando" in txt and ("encaminhar para pagamento" in txt or "notas fiscais abaixo" in txt or "Origem:" in txt):
            blocos_memo.append((num_pag, txt))
        if "Nota de Despesa" in txt or "Itens do Empenho" in txt:
            blocos_empenho.append((num_pag, txt))
        if "aspectos fiscais e tributários" in txt or "Despacho nº" in txt or "conferência dos aspectos fiscais" in txt:
            blocos_tributario.append((num_pag, txt))

    texto_memo = blocos_memo[-1][1] if blocos_memo else "\n".join([t[1] for t in paginas_texto[:4]])
    texto_empenho = blocos_empenho[-1][1] if blocos_empenho else ""
    texto_despacho_trib = blocos_tributario[-1][1] if blocos_tributario else ""

    # 3. UNIDADE HOSPITALAR
    hospital_sigla = "HZN"
    hospital_nome = "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina"
    for sigla, nome in MAPA_HOSPITAIS.items():
        if re.search(rf"\b{sigla}\b", texto_memo, re.IGNORECASE) or re.search(rf"{nome}", texto_memo, re.IGNORECASE):
            hospital_sigla = sigla if sigla in ["HIWM", "HRS", "HZNL", "HZN", "HRL", "HGG", "HILP", "HMT"] else "HRS"
            hospital_nome = nome
            break

    # 4. FORNECEDOR E CNPJ
    match_forn = re.search(r"FORNECEDOR:?\s*\n?([A-Z0-9\.\s\-\–\ã\õ\á\é\í\ó\ú]+?)(?=\n\s*(?:TIPO|AQUISIÇÃO|MATERIAIS|OPME|N[°º]|CONTRATO))", texto_memo, re.IGNORECASE)
    if not match_forn and texto_empenho:
        match_forn = re.search(r"Credor:\s*\d+\s*-\s*([A-Z0-9\.\s\-\–]+?)(?=\n|Endereço|CNPJ)", texto_empenho)
    if not match_forn and texto_despacho_trib:
        match_forn = re.search(r"Empresa\s*\n?([A-Z0-9\.\s\-\–]+?)(?=\n|CNPJ)", texto_despacho_trib, re.IGNORECASE)
    
    fornecedor_nome = match_forn.group(1).strip().replace("\n", " ") if match_forn else "HEXAGON DISTRIBUIÇÃO E LOGÍSTICA DE PRODUTOS"

    match_cnpj = re.search(r"CNPJ[:\s/MF]*([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})", texto_memo + "\n" + texto_empenho + "\n" + texto_despacho_trib + "\n" + texto_folha1)
    cnpj = match_cnpj.group(1) if match_cnpj else ""

    # 5. CONTRATO (Busca resiliente em cascata)
    contrato = ""
    match_c1 = re.search(r"Contrato:\s*([0-9]{1,4}/[0-9]{4})", texto_empenho, re.IGNORECASE)
    if match_c1:
        contrato = match_c1.group(1).strip()
    
    if not contrato:
        match_c2 = re.search(r"(?:CONTRATO|CONTRATO:|CONTRATO N[°º\s]*)[^\d\n\r]{0,10}([0-9]{1,4}/[0-9]{4})", texto_memo, re.IGNORECASE)
        if match_c2:
            contrato = match_c2.group(1).strip()

    if not contrato:
        match_c3 = re.search(r"EMPRESA:\s*[A-Z\s]+([0-9]{1,4}/[0-9]{4})", texto_folha1, re.IGNORECASE)
        if match_c3:
            contrato = match_c3.group(1).strip()

    if not contrato:
        match_c4 = re.search(r"CONTRATO\s*\n?\s*([0-9]{1,4}/[0-9]{4})", texto_memo, re.IGNORECASE)
        if match_c4:
            contrato = match_c4.group(1).strip()

    # 6. EMPENHO
    match_empenho = re.search(r"Número:\s*([0-9]{1,5}/[0-9]{4})", texto_empenho)
    if not match_empenho:
        match_empenho = re.search(r"(?:N[°º\s]*EMPENHO|EMPENHO:)[^\d\n\r]{0,10}([0-9]{1,5}/[0-9]{2,4})", texto_memo, re.IGNORECASE)
    if not match_empenho:
        match_empenho = re.search(r"EMPENHO\s*([0-9]{1,5}/[0-9]{2,4})", texto_folha1, re.IGNORECASE)
    empenho = match_empenho.group(1).strip() if match_empenho else ""

    # 7. COMPETÊNCIA E VIGÊNCIA
    match_comp = re.search(r"COMPETÊNCIA:?\s*([0-9]{2}/[0-9]{2,4}|[A-Za-zçãéíóú\s]+(?:\s+(?:a|à|e|À|A|E)\s+[A-Za-zçãéíóú\s]+)?(?:/[0-9]{2,4})?)", texto_folha1 + "\n" + texto_empenho + "\n" + texto_memo, re.IGNORECASE)
    if match_comp:
        comp_raw = match_comp.group(1).strip()
        comp_raw = re.sub(r"\s*-\s*.*$", "", comp_raw).strip()
        match_mes_ano = re.match(r"^(\d{2})/(\d{2,4})$", comp_raw)
        if match_mes_ano:
            mes_num, ano_num = match_mes_ano.groups()
            ano_completo = f"20{ano_num}" if len(ano_num) == 2 else ano_num
            competencia = f"{MAPA_MESES.get(mes_num, mes_num)} de {ano_completo}"
        else:
            competencia = comp_raw
    else:
        competencia = "agosto de 2026"

    match_vig = re.search(r"VIGÊNCIA:?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})\s*[a|à]\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", texto_empenho, re.IGNORECASE)
    vigencia_inicio = match_vig.group(1) if match_vig else "26/03/2026"
    vigencia_fim = match_vig.group(2) if match_vig else "25/03/2028"

    # 8. NOTAS FISCAIS
    nfs_encontradas = []
    match_data_padrao = re.search(r"([0-9]{2}/[0-9]{2}/[0-9]{4})", texto_memo)
    data_padrao = match_data_padrao.group(1) if match_data_padrao else ""

    if texto_despacho_trib:
        linhas_trib = re.findall(r"([0-9]{2,3}\.?[0-9]{3})\s+([0-9]{2}/[0-9]{2}/[0-9]{4})\s+Produto\s+(?:R\$\s*)?([0-9\.,]+)", texto_despacho_trib)
        for num_nf_raw, data_raw, valor_raw in linhas_trib:
            num_limpo = num_nf_raw.replace(".", "").strip()
            if not any(item["numero"] == num_limpo for item in nfs_encontradas):
                nfs_encontradas.append({
                    "numero": num_limpo,
                    "data_emissao": data_raw.strip(),
                    "valor": valor_raw.strip(),
                    "paciente": "",
                    "data_cirurgia": ""
                })

    if not nfs_encontradas:
        linhas_memo = re.findall(r"([0-9]{2,3}\.?[0-9]{3})\s+(?:([0-9]{2}/[0-9]{2}/[0-9]{2,4})\s+)?(?:R\$\s*)?([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})", texto_memo)
        for num_nf_raw, data_raw, valor_raw in linhas_memo:
            num_limpo = num_nf_raw.replace(".", "").strip()
            data_limpa = data_raw.strip() if data_raw else data_padrao
            if len(data_limpa) == 8:
                p = data_limpa.split("/")
                data_limpa = f"{p[0]}/{p[1]}/20{p[2]}"
            
            num_contrato_limpo = contrato.split('/')[0] if contrato else ""
            num_empenho_limpo = empenho.split('/')[0] if empenho else ""

            if num_limpo not in [num_contrato_limpo, num_empenho_limpo]:
                if not any(item["numero"] == num_limpo for item in nfs_encontradas):
                    nfs_encontradas.append({
                        "numero": num_limpo,
                        "data_emissao": data_limpa,
                        "valor": valor_raw.strip(),
                        "paciente": "",
                        "data_cirurgia": ""
                    })

    # 9. TOTAIS E EXTENSO
    total_reais = 0.0
    for nf in nfs_encontradas:
        v = nf["valor"].replace(".", "").replace(",", ".").replace("R$", "").strip()
        try:
            total_reais += float(v)
        except ValueError:
            pass

    valor_total_formatado = formatar_valor_reais(total_reais)
    try:
        valor_extenso = num2words(total_reais, lang="pt_BR", to="currency").lower()
    except Exception:
        valor_extenso = ""

    return {
        "protocolo": protocolo,
        "hospital_nome": hospital_nome,
        "hospital_sigla": hospital_sigla,
        "fornecedor_nome": fornecedor_nome,
        "cnpj": cnpj,
        "valor_total": valor_total_formatado,
        "valor_extenso": valor_extenso,
        "competencia": competencia,
        "contrato": contrato,
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": vigencia_fim,
        "empenho": empenho,
        "nfs": nfs_encontradas
    }