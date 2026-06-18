#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 20:38:57 2026

@author: farani
"""

import geopandas as gpd
import os

# 1. DEFINIÇÃO DE CAMINHOS
arquivo_zip = "terras_indigenas.zip"
arquivo_saida = "terras_indigenas.parquet"

print(f"⏳ Passo 1: Lendo '{arquivo_zip}' direto da pasta atual...")
try:
    gdf = gpd.read_file(f"zip://{arquivo_zip}")
    print(f"✅ Base de Terras Indígenas carregada! Registros originais: {len(gdf)}")
except Exception as e:
    print(f"❌ Erro ao ler '{arquivo_zip}': {e}")
    print("Verifique se o arquivo está na mesma pasta do script e com o nome correto.")
    exit()

# Inspeção preventiva de colunas no console
print("\n📋 Colunas encontradas na base de TIs:")
print(list(gdf.columns))

print("\n👀 Amostra dos dados (primeiras 2 linhas):")
print(gdf.head(2))

# 2. IDENTIFICAÇÃO DA COLUNA DE NOME e LIMPEZA
print("\n✂️ Passo 2: Padronizando atributos e removendo colunas pesadas...")

# Mapeamento inteligente para os padrões mais comuns da Funai (ex: 'terrai_nom', 'nome', 'nome_ti')
col_nome = None
for col in gdf.columns:
    if col.lower() in ['terrai_nom', 'nome', 'nome_ti', 'etnia', 'terrai_sig']:
        col_nome = col
        break

if col_nome:
    print(f"🔍 Coluna de nome identificada: '{col_nome}'")
    gdf['nome_ti'] = gdf[col_nome].astype(str).str.strip().str.upper()
else:
    print("⚠️ Nenhuma coluna de nome óbvia encontrada. Adotando nome padrão 'TERRA INDÍGENA'")
    gdf['nome_ti'] = "TERRA INDÍGENA"

# Mantém estritamente o nome e a geometria (essencial para poupar memória RAM no Streamlit)
colunas_essenciais = ['nome_ti', 'geometry']
gdf_filtrado = gdf[colunas_essenciais].copy()
gdf_filtrado = gdf_filtrado[gdf_filtrado.geometry.notna()]

# 3. SIMPLIFICAÇÃO GEOMÉTRICA DE POLÍGONOS (Tolerância: 150 metros)
print("\n⚡ Passo 3: Otimizando as fronteiras dos polígonos (Tolerância: 150m)...")
gdf_m = gdf_filtrado.to_crs(epsg=5880) # Projeta temporariamente para metros

# Simplifica os polígonos mantendo a integridade topológica das bordas
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=150, preserve_topology=True)
gdf_final = gdf_m.to_crs(epsg=4326) # Retorna para graus (WGS84)

# 4. EXPORTAÇÃO PARA GEOPARQUET
os.makedirs("dados", exist_ok=True)
print(f"\n💾 Passo 4: Exportando base otimizada para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

# Cálculo do ganho de performance
tamanho_bytes = os.path.getsize(arquivo_saida)
tamanho_mb = tamanho_bytes / (1024 * 1024)
print(f"\n✨ SUCESSO! Camada de Terras Indígenas processada.")
print(f"📦 Tamanho final do arquivo unificado: {tamanho_mb:.2f} MB")