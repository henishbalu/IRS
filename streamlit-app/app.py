import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")

def process_ficheiro(uploaded_file, ano_alvo):
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
                        compra['Produto'], usar_qtd,
                        venda['Data'].year, venda['Data'].month, venda['Data'].day,
                        valor_venda,
                        compra['Data'].year, compra['Data'].month, compra['Data'].day,
                        valor_compra,
                        total_comissoes
                    ])

                    qtd_restante_compra -= usar_qtd
                    vendas_isin.at[venda_idx, 'quantidade_restante'] -= usar_qtd
                    vendas_isin.at[venda_idx, 'valor_restante'] -= valor_venda

                    if vendas_isin.at[venda_idx, 'quantidade_restante'] == 0:
                        venda_idx += 1

        fifo_df = pd.DataFrame(fifo_result, columns=[
            "Produto", "Quantidade", "Ano Venda", "Mês Venda", "Dia Venda", "Valor Venda",
            "Ano Compra", "Mês Compra", "Dia Compra", "Valor Compra", "Comissões"
        ])
        fifo_df["Mais-Valia"] = fifo_df["Valor Venda"] + fifo_df["Valor Compra"] + fifo_df["Comissões"]

        resumo_produto = (
            fifo_df.groupby("Produto")
            .agg({"Valor Venda": "sum", "Valor Compra": "sum", "Comissões": "sum"})
            .assign(Ganho_Perda=lambda x: x["Valor Venda"] + x["Valor Compra"] + x["Comissões"])
            .reset_index()
        )

        st.subheader("Resultado FIFO")
        st.dataframe(fifo_df, use_container_width=True)

        st.subheader("Resumo de Ganhos/Perdas por Produto")
        st.dataframe(resumo_produto, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao processar o ficheiro: {e}")

def main():
    st.title("Calculadora de Mais-Valias (FIFO)")

    uploaded_file = st.file_uploader("Escolhe o ficheiro de transações", type=["csv", "xls", "xlsx"])
    if uploaded_file:
        ano = st.number_input("Ano para analisar", min_value=2000, max_value=2100, value=2024)
        if st.button("Calcular Mais-Valias"):
            process_ficheiro(uploaded_file, ano)

if __name__ == "__main__":
    main()
