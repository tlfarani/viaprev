import geopandas as gpd
import pandas as pd
import os

# 1. DEFINIÇÃO DOS ARQUIVOS NA MESMA PASTA
arquivo_est_zip = "rodovias_SP.zip"
arquivo_fed_parquet = "rodovias_federais.parquet"
diretorio_saida = "dados"
arquivo_final = os.path.join(diretorio_saida, "rodovias.parquet")

print("⏳ Passo 1: Lendo as rodovias estaduais de São Paulo...")
try:
    gdf_sp = gpd.read_file(f"zip://{arquivo_est_zip}")
    print(f"✅ Base estadual carregada! Registros originais: {len(gdf_sp)}")
except Exception as e:
    print(f"❌ Erro ao ler 'rodovias_SP.zip': {e}")
    exit()

# Inspeção preventiva de colunas no console
print("\n📋 Colunas encontradas na base estadual:")
print(list(gdf_sp.columns))

# 2. IDENTIFICAÇÃO E PADRONIZAÇÃO DA RODODVIA ESTADUAL
print("\n⚙️ Passo 2: Padronizando nomenclatura para o padrão 'SP-XXX'...")
col_identificadora = None
for col in gdf_sp.columns:
    if col.lower() in ['rodovia', 'sigla', 'nome', 'nm_rodovia', 'sgr_rodovi', 'cd_rodovia']:
        col_identificadora = col
        break

if col_identificadora:
    print(f"🔍 Coluna selecionada para o filtro: '{col_identificadora}'")
    # Limpa o texto, remove espaços e garante formato padrão texto
    gdf_sp['rodovia'] = gdf_sp[col_identificadora].astype(str).str.upper().str.strip()
    
    # Se a coluna tiver apenas números (ex: 310 ou 310.0), limpa e adiciona o prefixo SP-
    gdf_sp['rodovia'] = gdf_sp['rodovia'].str.replace('.0', '', regex=False)
    gdf_sp['rodovia'] = gdf_sp['rodovia'].apply(lambda x: f"SP-{x.zfill(3)}" if not x.startswith('SP') and x.isdigit() else x)
else:
    print("⚠️ Coluna de identificação óbvia não encontrada. Adotando nome genérico 'SP-ESTADUAL'")
    gdf_sp['rodovia'] = "SP-ESTADUAL"

# Adiciona metadados fixos de controle
gdf_sp['sg_uf'] = "SP"
gdf_sp['ds_jurisdi'] = "Estadual"

# Mantém apenas as colunas estruturais necessárias para economizar memória RAM
colunas_limpas = ['rodovia', 'sg_uf', 'ds_jurisdi', 'geometry']
gdf_sp_limpo = gdf_sp[colunas_limpas].copy()

# 3. SIMPLIFICAÇÃO GEOMÉTRICA (Douglas-Peucker 200 metros)
print("\n⚡ Passo 3: Aplicando simplificação geométrica na malha estadual...")
gdf_sp_m = gdf_sp_limpo.to_crs(epsg=5880) # Projeta para metros (Sirgas2000 / Brazil Polyconic)
gdf_sp_m['geometry'] = gdf_sp_m.geometry.simplify(tolerance=200, preserve_topology=True)
gdf_sp_final = gdf_sp_m.to_crs(epsg=4326) # Retorna para graus (WGS84)

# 4. CARREGAMENTO DA MALHA FEDERAL JÁ PROCESSADA
print("\n📂 Passo 4: Carregando a malha federal otimizada existente...")
if os.path.exists(arquivo_fed_parquet):
    gdf_fed = gpd.read_parquet(arquivo_fed_parquet)
    print(f"✅ Malha federal carregada! Registros: {len(gdf_fed)}")
else:
    print(f"❌ Arquivo '{arquivo_fed_parquet}' não foi encontrado nesta pasta. Rode o script federal primeiro.")
    exit()

# 5. FUSÃO E CONCATENAÇÃO DAS DUAS MALHAS
print("\n🔄 Passo 5: Unificando malhas (BRs + SPs) em uma única cobertura...")
# Garante o alinhamento das colunas antes de juntar
gdf_combined = pd.concat([gdf_fed, gdf_sp_final], ignore_index=True)
gdf_combined = gpd.GeoDataFrame(gdf_combined, geometry='geometry', crs="EPSG:4326")

# Remove registros nulos ou inválidos por segurança topológica
gdf_combined = gdf_combined[gdf_combined.geometry.notna()]

# 6. SALVAMENTO BINÁRIO DO PARQUET UNIFICADO
os.makedirs(diretorio_saida, exist_ok=True)
print(f"💾 Passo 6: Exportando arquivo consolidado para '{arquivo_final}'...")
gdf_combined.to_parquet(arquivo_final)

# Cálculo final de performance
tamanho_mb = os.path.getsize(arquivo_final) / (1024 * 1024)
print(f"\n✨ SUCESSO! Malha combinada gerada com {len(gdf_combined)} trechos totais.")
print(f"📦 Tamanho final do arquivo unificado: {tamanho_mb:.2f} MB")