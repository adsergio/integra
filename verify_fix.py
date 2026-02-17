import pandas as pd
from integra import extrair_lancamentos_por_coordenadas
import sys

pdf_path = r"c:\Users\Sergio\Documents\Apps-Contabilidade\integra\extratos\extrato-bradesco.pdf"

print("Iniciando verificação da extração...")
try:
    df = extrair_lancamentos_por_coordenadas(pdf_path, debug=True)
    if df.empty:
        print("FALHA: O DataFrame retornado está vazio.")
    else:
        print(f"SUCESSO: Extraídos {len(df)} lançamentos.")
        print(df[["Data", "Lancamento", "Valor"]].head(20).to_string())
        
        # Check specific known problematic rows (from previous diagnosis)
        # Page 5 had "LIQUIDACAO DE COBRANCA" followed by value
        check = df[df["Lancamento"].str.contains("LIQUIDACAO DE COBRANCA", na=False)]
        if not check.empty:
            print("\nVerificação de 'LIQUIDACAO DE COBRANCA': Encontrado!")
            print(check.head(2).to_string())
        else:
            print("\nAVISO: 'LIQUIDACAO DE COBRANCA' não encontrado (pode ser problema se existir no PDF).")

except Exception as e:
    print(f"ERRO DE EXECUÇÃO: {e}")
    import traceback
    traceback.print_exc()
