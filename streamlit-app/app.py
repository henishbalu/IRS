import streamlit as st
import pandas as pd
from io import StringIO
import json
from datetime import datetime

st.set_page_config(layout="wide")  # Default layout for the app
with open("codigos_paises.json", encoding="utf-8") as f:
    paises_info_list = json.load(f)
    paises_info = {item['Cód. Alf2']: item for item in paises_info_list}

def process_ficheiro_degiro(uploaded_file, ano_alvo):
    try:
        df = pd.read_csv(uploaded_file, delimiter=',')
        df.columns = df.columns.str.strip()

        df['Valor'] = df['Valor'].astype(str).str.replace('\u00a0', '').str.replace(',', '.').astype(float)
        df['Custos de transação'] = df['Custos de transação'].fillna('0').astype(str).str.replace('\u00a0', '').str.replace(',', '.').astype(float)
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df['Quantidade'] = df['Quantidade'].astype(int)
        df['ISIN'] = df['ISIN'].str.strip()

        compras = df[df['Valor'] < 0].copy()
        vendas = df[(df['Valor'] > 0) & (df['Data'].dt.year == ano_alvo)].copy()
        compras['Quantidade'] = compras['Quantidade'].abs()
        vendas['Quantidade'] = vendas['Quantidade'].abs()

        compras = compras.sort_values(by='Data').reset_index(drop=True)
        vendas = vendas.sort_values(by='Data').reset_index(drop=True)

        vendas['quantidade_restante'] = vendas['Quantidade']
        vendas['valor_restante'] = vendas['Valor']
        vendas['quantidade_total'] = vendas['Quantidade']
        vendas['valor_total'] = vendas['Valor']
        vendas['comissao_usada'] = False

        fifo_result = []

        for isin in set(vendas['ISIN']).intersection(set(compras['ISIN'])):
            compras_isin = compras[compras['ISIN'] == isin].copy().reset_index(drop=True)
            vendas_isin = vendas[vendas['ISIN'] == isin].copy().reset_index(drop=True)
            venda_idx = 0

            for _, compra in compras_isin.iterrows():
                qtd_restante_compra = compra['Quantidade']
                preco_unit_compra = compra['Valor'] / compra['Quantidade']

                while qtd_restante_compra > 0 and venda_idx < len(vendas_isin):
                    venda = vendas_isin.loc[venda_idx]
                    if venda['quantidade_restante'] == 0:
                        venda_idx += 1
                        continue

                    usar_qtd = min(qtd_restante_compra, venda['quantidade_restante'])
                    valor_venda = round(venda['valor_total'] * (usar_qtd / venda['quantidade_total']), 2)
                    valor_compra = round(preco_unit_compra * usar_qtd, 2)

                    comissao_compra = compra['Custos de transação'] * (usar_qtd / compra['Quantidade'])
                    comissao_venda = 0
                    if not vendas_isin.at[venda_idx, 'comissao_usada']:
                        comissao_venda = venda['Custos de transação']
                        vendas_isin.at[venda_idx, 'comissao_usada'] = True

                    total_comissoes = round(comissao_compra + comissao_venda, 2)

                    fifo_result.append([
                        venda['Data'].year, venda['Data'].month, venda['Data'].day,
                        valor_venda,
                        compra['Data'].year, compra['Data'].month, compra['Data'].day,
                        valor_compra,
                        total_comissoes,compra['Produto'], compra['ISIN'], usar_qtd,
                    ])

                    qtd_restante_compra -= usar_qtd
                    vendas_isin.at[venda_idx, 'quantidade_restante'] -= usar_qtd
                    vendas_isin.at[venda_idx, 'valor_restante'] -= valor_venda

                    if vendas_isin.at[venda_idx, 'quantidade_restante'] == 0:
                        venda_idx += 1

        fifo_df = pd.DataFrame(fifo_result, columns=[
            "Ano Venda", "Mês Venda", "Dia Venda", "Valor Venda",
            "Ano Compra", "Mês Compra", "Dia Compra", "Valor Compra", "Despesas e Encargos","Produto", "ISIN", "Quantidade"
        ])
        fifo_df["Mais-Valia"] = round(fifo_df["Valor Venda"] + fifo_df["Valor Compra"] + fifo_df["Despesas e Encargos"],2)

        # === Enriquecer com País e Cód. Num com base no novo JSON ===
        fifo_df["Código País"] = fifo_df["ISIN"].str[:2]
        fifo_df["País"] = fifo_df["Código País"].map(lambda c: paises_info.get(c, {}).get("Designação", "Desconhecido").title())
        fifo_df["Cód. Num."] = fifo_df["Código País"].map(lambda c: paises_info.get(c, {}).get("Cód.Num.", ""))
        fifo_df["Código e País"] = fifo_df["Cód. Num."].astype(str) + " - " + fifo_df["País"]

        resumo_produto = (
            fifo_df.groupby("Produto")
            .agg({"Valor Venda": "sum", "Valor Compra": "sum", "Despesas e Encargos": "sum"})
            .assign(Ganho_Perda=lambda x: x["Valor Venda"] + x["Valor Compra"] + x["Despesas e Encargos"])
            .reset_index()
        )
        
        def render_grouped_table(df):

            # Define groups
            principal_cols = ["Código e País","Ano Venda", "Mês Venda", "Dia Venda", "Valor Venda", "Ano Compra", "Mês Compra", "Dia Compra", "Valor Compra","Despesas e Encargos"]
            auxiliar_cols = ["Produto", "Quantidade", "Mais-Valia"]

            df = df[principal_cols + auxiliar_cols]  # reorder

            # Build HTML
            html = StringIO()
            html.write('<table border="1" style="width:100%; border-collapse: collapse;">')
            html.write('<thead><tr>')

            # First header row (groups)
            html.write(f'<th colspan="{len(principal_cols)}" style="background:#f0f0f0; text-align: center; font-size: 16px; font-weight: bold;">Principal</th>')
            html.write(f'<th colspan="{len(auxiliar_cols)}" style="background:#f0f0f0; text-align: center; font-size: 16px;">Auxiliar</th>')
            html.write('</tr><tr>')

            # Second header row (individual columns)
            for col in principal_cols + auxiliar_cols:
                html.write(f'<th>{col}</th>')
            html.write('</tr></thead><tbody>')

            # Table body
            for _, row in df.iterrows():
                html.write('<tr>')
                for col in principal_cols + auxiliar_cols:
                    html.write(f'<td>{row[col]}</td>')
                html.write('</tr>')

            html.write('</tbody></table>')
            st.markdown(html.getvalue(), unsafe_allow_html=True)
        
        st.subheader("Resultado FIFO")
        render_grouped_table(fifo_df)

        st.subheader("Resumo de Ganhos/Perdas por Produto")

        # Format the relevant columns with the € symbol
        resumo_produto[["Valor Venda", "Valor Compra", "Despesas e Encargos", "Ganho_Perda"]] = resumo_produto[
            ["Valor Venda", "Valor Compra", "Despesas e Encargos", "Ganho_Perda"]
        ].map(lambda x: f"{x:,.2f} €")

        # Display the formatted DataFrame using st.table
        st.table(resumo_produto)

    except Exception as e:
        st.error(f"Erro ao processar o ficheiro: {e}")

def process_ficheiro_trading212(uploaded_file, ano_alvo):
    try:
        # Example processing logic for TRADING 212
        df = pd.read_csv(uploaded_file, delimiter=',')
        st.write("Em desenvolvimento")
        # Add your TRADING 212-specific processing logic here 
        # Display the uploaded file as a DataFrame for now
    except Exception as e:
        st.error(f"Erro ao processar o ficheiro: {e}")

def main():
    st.title("Calculadora de apoio de Mais-Valias e Menos-Valias no IRS")

    # Add a selectbox to choose between DEGIRO and TRADING 212
    platform = st.selectbox("Escolha a plataforma de transações", ["DEGIRO", "TRADING 212"])

    uploaded_file = st.file_uploader("Escolhe o ficheiro de transações", type=["csv"])
    if uploaded_file:
        ano = st.number_input("Escolha o ano para analisar", min_value=2000, max_value=datetime.now().year, value=2024)
        if st.button("Calcular Valores"):
            if platform == "DEGIRO":
                process_ficheiro_degiro(uploaded_file, ano)
            elif platform == "TRADING 212":
                process_ficheiro_trading212(uploaded_file, ano)

if __name__ == "__main__":
    main()
