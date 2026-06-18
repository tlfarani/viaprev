import geopandas as gpd
import os

# 1. DEFINIÇÃO DE CAMINHOS
arquivo_zip = "Rios.zip"
arquivo_saida = "hidrografia.parquet"

print(f"⏳ Passo 1: Lendo 'Rios.zip' direto da pasta atual...")
try:
    gdf = gpd.read_file(f"zip://{arquivo_zip}")
    print(f"✅ Base hidrográfica carregada! Registros originais: {len(gdf)}")
except Exception as e:
    print(f"❌ Erro ao ler '{arquivo_zip}': {e}")
    exit()

# 2. FILTRAGEM PELA COLUNA EXATA (NORIOCOMP)
print("\n✂️ Passo 2: Padronizando coluna de nomenclatura...")
col_nome_exata = 'NORIOCOMP'

if col_nome_exata in gdf.columns:
    gdf['nome_rio'] = gdf[col_nome_exata].astype(str).str.strip().str.upper()
else:
    print("❌ Coluna 'NORIOCOMP' não encontrada.")
    exit()

# Mantém apenas as colunas essenciais para economizar RAM no Streamlit
colunas_essenciais = ['nome_rio', 'geometry']
gdf_filtrado = gdf[colunas_essenciais].copy()
gdf_filtrado = gdf_filtrado[gdf_filtrado.geometry.notna()]

# 3. SIMPLIFICAÇÃO GEOMÉTRICA AGRESSIVA (Calibrada para 500 metros)
print("\n⚡ Passo 3: Aplicando simplificação geométrica otimizada (Tolerância: 500m)...")
gdf_m = gdf_filtrado.to_crs(epsg=5880) # Projeta temporariamente para metros
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=500, preserve_topology=True)
gdf_final = gdf_m.to_crs(epsg=4326) # Retorna para graus (WGS84)

# 4. EXPORTAÇÃO
os.makedirs("dados", exist_ok=True)
print(f"\n💾 Passo 4: Exportando arquivo final otimizado para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

# Cálculo final de peso e verificação de segurança no console (Corrigido sem 'st')
tamanho_bytes = os.path.getsize(arquivo_saida)
tamanho_mb = tamanho_bytes / (1024 * 1024)
print(f"\n✨ SUCESSO! Base de hidrografia processada.")
print(f"📦 Tamanho final do arquivo unificado: {tamanho_mb:.2f} MB")

if tamanho_mb > 8.0:
    print(f"\n⚠️ AVISO: O arquivo ainda está com {tamanho_mb:.1f} MB.")
    print("Caso sinta lentidão no Streamlit, aumente a tolerância para 1000 no Passo 3.")
else:
    print("\n🚀 Arquivo em tamanho ideal para deploy no Streamlit Cloud!")