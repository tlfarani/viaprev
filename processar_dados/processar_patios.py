#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 18:35:27 2026

@author: farani
"""

import geopandas as gpd
import pandas as pd

print("⏳ Lendo e padronizando as bases do GeoDNIT...")

# 1. Carregar e classificar cada camada
# O geopandas lê arquivos zip se usarmos o prefixo zip://
try:
    manutencao = gpd.read_file("zip://vw_epl_manutencao.zip")
    manutencao['tipo_logistico'] = 'Oficina de Manutenção'
except Exception as e:
    print(f"Erro ao ler manutenção: {e}")
    manutencao = gpd.GeoDataFrame()

try:
    patios = gpd.read_file("zip://vw_epl_patios.zip")
    patios['tipo_logistico'] = 'Pátio Operacional'
except Exception as e:
    print(f"Erro ao ler pátios: {e}")
    patios = gpd.GeoDataFrame()

try:
    terminais = gpd.read_file("zip://vw_epl_terminais.zip")
    terminais['tipo_logistico'] = 'Terminal de Cargas'
except Exception as e:
    print(f"Erro ao ler terminais: {e}")
    terminais = gpd.GeoDataFrame()

# 2. Unificar os GeoDataFrames em uma lista para tratamento
camadas = [manutencao, patios, terminais]
camadas_validas = [c for c in camadas if not c.empty]

if not camadas_validas:
    print("❌ Nenhuma camada foi carregada com sucesso. Verifique os nomes dos arquivos zip.")
    exit()

# 3. Padronizar a coluna de Nome
# Arquivos governamentais variam muito (NOME, nome, NM_PATIO, etc.)
# Vamos varrer as colunas e forçar uma coluna padrão chamada 'nome'
for g_df in camadas_validas:
    colunas_possiveis = [col for col in g_df.columns if 'nome' in col.lower() or 'nm_' in col.lower() or 'descr' in col.lower()]
    if colunas_possiveis:
        col_nome_original = colunas_possiveis[0]
        g_df['nome'] = g_df[col_nome_original]
    else:
        g_df['nome'] = "Instalação Sem Nome"

# 4. Concatenar todas as tabelas em um único GeoDataFrame unificado
print("🔄 Unificando bases em uma única malha de pontos...")
gdf_patios_oficinas = pd.concat([c[['nome', 'tipo_logistico', 'geometry']] for c in camadas_validas], ignore_index=True)
gdf_patios_oficinas = gpd.GeoDataFrame(gdf_patios_oficinas, geometry='geometry')

# 5. Garantir que o sistema de coordenadas é o WGS84 (Graus - EPSG:4326)
if gdf_patios_oficinas.crs is None:
    # Caso venha sem CRS, geralmente essas bases federais usam SIRGAS 2000 (EPSG:4674) ou WGS84
    gdf_patios_oficinas.set_crs(epsg=4674, inplace=True)

# Converte para WGS84 que é o padrão exigido pelo nosso app
gdf_patios_oficinas = gdf_patios_oficinas.to_crs(epsg=4326)

# 6. Exportar para GeoParquet
nome_saida = "patios_oficinas.parquet"
gdf_patios_oficinas.to_parquet(nome_saida)

print(f"✅ Sucesso! Arquivo '{nome_saida}' gerado com {len(gdf_patios_oficinas)} pontos logísticos.")