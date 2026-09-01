import io
import os
import pandas as pd
import streamlit as st
from docxtpl import DocxTemplate
from extractor import extrair_dados_processo, formatar_valor_reais
from num2words import num2words

st.set_page_config(
    page_title="Gerador de Despacho OPME | DAH-FUNEAS",
    page_icon="📄",
    layout="wide"
)

# Equipe da Divisão de Auditoria Hospitalar
MEMBROS_EQUIPE = [
    {"nome": "Julia Veiga Ramalho", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Emily Gomes Trevisan", "cargo": "Chefe de Setor – DAH/FUNEAS"},
    {"nome": "Michele Prestes Jientara", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Soraya Pacheco dos Santos Lima", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Outro (Digitar manualmente)", "cargo": "DAH/FUNEAS"}
]

st.title("🏥 Gerador de Despacho de OPME - DAH / FUNEAS")
st.markdown("Extração automatizada e emissão de despachos de auditoria (100% Local / LGPD).")

# Barra Lateral: Identificação do Auditor
st.sidebar.header("👤 Responsável pela Análise")
nomes_opcoes = [m["nome"] for m in MEMBROS_EQUIPE]
nome_selecionado = st.sidebar.selectbox("Selecione seu nome:", nomes_opcoes, index=0)

if nome_selecionado == "Outro (Digitar manualmente)":
    auditor_nome = st.sidebar.text_input("Nome completo:")
    auditor_cargo = st.sidebar.text_input("Cargo:", value="Assistente Administrativo – DAH/FUNEAS")
else:
    item_membro = next(m for m in MEMBROS_EQUIPE if m["nome"] == nome_selecionado)
    auditor_nome = item_membro["nome"]
    auditor_cargo = item_membro["cargo"]

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Elaborado por:**\n\n**{auditor_nome}**\n\n*{auditor_cargo}*")
st.sidebar.markdown("**Homologador Fixo:**\n\n**Evandro Freire Tirapelle**\n\n*Chefe da Divisão de Auditoria Hospitalar – FUNEAS*")

# 1. Upload do PDF do Processo
st.subheader("1. Carregar Arquivo do Processo")
arquivo_pdf = st.file_uploader("Arraste ou selecione o PDF do eProtocolo:", type=["pdf"])

if arquivo_pdf is not None:
    if "dados_extraidos" not in st.session_state or st.session_state.get("nome_arquivo") != arquivo_pdf.name:
        with st.spinner("Extraindo informações do processo..."):
            pdf_bytes = arquivo_pdf.read()
            st.session_state["dados_extraidos"] = extrair_dados_processo(pdf_bytes)
            st.session_state["nome_arquivo"] = arquivo_pdf.name

    dados = st.session_state["dados_extraidos"]
    st.success("Dados extraídos com sucesso! Revise as informações abaixo:")

    # 2. Dados Gerais
    st.subheader("2. Dados Gerais do Processo")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        protocolo = st.text_input("Protocolo nº", value=dados["protocolo"])
        hospital_sigla = st.text_input("Sigla da Unidade", value=dados["hospital_sigla"])
        hospital_nome = st.text_input("Nome do Hospital", value=dados["hospital_nome"])

    with col2:
        fornecedor_nome = st.text_input("Fornecedor", value=dados["fornecedor_nome"])
        cnpj = st.text_input("CNPJ", value=dados["cnpj"])
        competencia = st.text_input("Competência", value=dados["competencia"])

    with col3:
        contrato = st.text_input("Contrato nº", value=dados["contrato"])
        empenho = st.text_input("Nota de Despesa/Empenho", value=dados["empenho"])
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            vig_inicio = st.text_input("Vigência Início", value=dados["vigencia_inicio"])
        with col_v2:
            vig_fim = st.text_input("Vigência Fim", value=dados["vigencia_fim"])

    # 3. Tabela de Notas Fiscais
    st.subheader("3. Relação de Notas Fiscais e Pacientes")
    st.caption("Preencha diretamente na tabela o Nome do Paciente e a Data da Cirurgia.")

    df_nfs = pd.DataFrame(dados["nfs"])
    if df_nfs.empty:
        df_nfs = pd.DataFrame(columns=["numero", "data_emissao", "valor", "paciente", "data_cirurgia"])

    df_editado = st.data_editor(
        df_nfs,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "numero": "Nº NF",
            "data_emissao": "Data Emissão",
            "valor": "Valor (R$)",
            "paciente": "Nome do Paciente",
            "data_cirurgia": "Data Cirurgia (DD/MM/AAAA)"
        }
    )

    # Recalcula total e checa alçada de R$ 20.000,00
    total_calculado = 0.0
    for _, row in df_editado.iterrows():
        try:
            v = str(row["valor"]).replace(".", "").replace(",", ".").replace("R$", "").strip()
            total_calculado += float(v)
        except Exception:
            pass

    valor_total_str = formatar_valor_reais(total_calculado)
    try:
        valor_extenso_str = num2words(total_calculado, lang="pt_BR", to="currency").lower()
    except Exception:
        valor_extenso_str = ""

    exige_diretoria = total_calculado > 20000.0

    st.markdown(f"**Valor Total Consolidado:** R$ {valor_total_str} (*{valor_extenso_str}*)")
    
    if exige_diretoria:
        st.warning("⚠️ **Alçada Superior (> R$ 20.000,00):** O despacho incluirá a assinatura da Diretora Técnica (Dra. Acácia Nasr).")
    else:
        st.info("ℹ️ **Alçada Padrão (≤ R$ 20.000,00):** O despacho será assinado pelo Analista e pela Chefia da Divisão.")

    # 4. Parecer
    st.subheader("4. Parecer da Auditoria")
    tem_inconformidade = st.radio(
        "Foram detectadas inconformidades/glosas nas NFs ou documentos?",
        options=["Não (Parecer Favorável)", "Sim (Retorno à Unidade de Origem)"],
        index=0
    )

    texto_inconformidade = ""
    if tem_inconformidade == "Sim (Retorno à Unidade de Origem)":
        texto_inconformidade = st.text_area(
            "Descreva as inconformidades por paciente/NF:",
            placeholder="Exemplo:\n• Nota Fiscal nº 215316 — Paciente: JOÃO DA SILVA: Ausência de relatório de saída de sala.",
            height=120
        )

    # 5. Geração e Download
    st.subheader("5. Gerar Despacho Word (.docx)")
    caminho_template = os.path.join(os.path.dirname(__file__), "templates", "modelo_despacho.docx")

    if not os.path.exists(caminho_template):
        st.warning(f"Coloque o arquivo do modelo Word em: `{caminho_template}` para habilitar a geração.")
    else:
        if st.button("📝 Gerar Documento Despacho"):
            doc = DocxTemplate(caminho_template)
            lista_nfs_context = df_editado.to_dict(orient="records")

            contexto = {
                "protocolo": protocolo,
                "hospital_nome": hospital_nome,
                "hospital_sigla": hospital_sigla,
                "fornecedor_nome": fornecedor_nome,
                "cnpj": cnpj,
                "valor_total": valor_total_str,
                "valor_extenso": valor_extenso_str,
                "competencia": competencia,
                "contrato": contrato,
                "vigencia_inicio": vig_inicio,
                "vigencia_fim": vig_fim,
                "empenho": empenho,
                "nfs": lista_nfs_context,
                "tem_inconformidade": (tem_inconformidade != "Não (Parecer Favorável)"),
                "texto_inconformidade": texto_inconformidade,
                "assinante_elaborador": auditor_nome,
                "cargo_elaborador": auditor_cargo,
                "exige_diretoria": exige_diretoria
            }

            doc.render(contexto)

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            primeiro_nome_forn = fornecedor_nome.split()[0].replace("/", "_")
            nome_saida = f"DESPACHO_{hospital_sigla}_OPME_{protocolo}_{primeiro_nome_forn}.docx"

            st.download_button(
                label="📥 Baixar Despacho em Word (.docx)",
                data=buffer,
                file_name=nome_saida,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )