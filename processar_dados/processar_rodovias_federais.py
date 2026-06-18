import geopandas as gpd
import os

# 1. DEFINIÇÃO DE CAMINHOS
#caminho_desktop = os.path.expanduser("~/Desktop")
#arquivo_zip = os.path.join(caminho_desktop, "rodovias.zip")
arquivo_saida = "rodovias_federais.parquet"

print("⏳ Lendo 'rodovias_federais.zip' do DNIT direto do Desktop...")
gdf = gpd.read_file("zip://rodovias_federais.zip")
print(f"✅ Arquivo carregado! Registros originais: {len(gdf)}")

# 2. SELEÇÃO DE COLUNAS ESSENCIAIS
colunas_essenciais = ['vl_br', 'sg_uf', 'ds_jurisdi', 'ds_superfi', 'geometry']
gdf_filtrado = gdf[colunas_essenciais].copy()

# 3. CRIAÇÃO DE UMA COLUNA DE IDENTIFICAÇÃO FORMATADA
gdf_filtrado['rodovia'] = "BR-" + gdf_filtrado['vl_br'].astype(str).str.zfill(3)
gdf_filtrado = gdf_filtrado[gdf_filtrado.geometry.notna()]

# 4. O PULO DO GATO: SIMPLIFICAÇÃO GEOMÉTRICA (Redução drástica de tamanho)
print("\n⚡ Iniciando simplificação geométrica de alta performance...")
# Para simplificar em metros, precisamos projetar temporariamente para o CRS do Brasil (EPSG:5880)
gdf_m = gdf_filtrado.to_crs(epsg=5880)

# Simplifica mantendo uma tolerância de 200 metros. 
# Preserve_topology=True impede que as linhas se quebrem ou virem nós inválidos
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=200, preserve_topology=True)

# Retorna para WGS84 (Graus) que o Folium exige
print("🌍 Convertendo de volta para WGS84 (EPSG:4326)...")
gdf_final = gdf_m.to_crs(epsg=4326)

# 5. SALVAMENTO
os.makedirs("dados", exist_ok=True)
print(f"💾 Salvando arquivo final ultra-compactado em: '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

# Verifica o tamanho do arquivo gerado
tamanho_bytes = os.path.getsize(arquivo_saida)
tamanho_mb = tamanho_bytes / (1024 * 1024)
print(f"✨ Concluído! Tamanho final do arquivo: {tamanho_mb:.2f} MB")