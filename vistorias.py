import streamlit as st
import geopandas as gpd
import geobr
import networkx as nx
import folium
from streamlit_folium import st_folium
from shapely.ops import substring
from shapely.geometry import LineString, Point, box
import os

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide", 
    page_title="Planejador Nacional de Vistoria Ferroviária",
    page_icon="🚊"
)

st.title("🚊 Planejador de Vistoria Ferroviária com Matriz de Risco")
st.markdown("Análise de criticidade socioambiental baseada em Combinação Linear Ponderada (Análise Multicritério).")

# --- 1. INICIALIZAÇÃO DA MEMÓRIA DO APP ---
if "dados_calculados" not in st.session_state:
    st.session_state.dados_calculados = None

# --- 2. CARREGAMENTO DOS DADOS NACIONAIS BASE ---
@st.cache_data(show_spinner=False)
def carregar_bases_nacionais():
    sedes_municipios = geobr.read_municipal_seat()
    try:
        malha_ferroviaria = gpd.read_parquet("dados/malha_ferroviaria.parquet")
        if malha_ferroviaria.crs is None:
            malha_ferroviaria.set_crs(epsg=4326, inplace=True)
    except Exception:
        st.sidebar.error("❌ Arquivo 'dados/malha_ferroviaria.parquet' ausente!")
        malha_ferroviaria = gpd.GeoDataFrame(geometry=[LineString([(0,0), (0,0)])], crs="EPSG:4326")
    return malha_ferroviaria, sedes_municipios

with st.spinner("Carregando bases geográficas de apoio..."):
    malha, sedes = carregar_bases_nacionais()

# --- 3. FUNÇÕES AUXILIARES DE GRAFOS E ATRAÇÃO ---
def extrair_grafo_ferroviario(gdf_ferrovia):
    G = nx.Graph()
    for idx, row in gdf_ferrovia.iterrows():
        geom = row.geometry
        if geom.is_empty: continue
        linhas = [geom] if geom.geom_type == 'LineString' else geom.geoms
        for linha in list(linhas):
            coords = list(linha.coords)
            if len(coords) < 2: continue
            for i in range(len(coords) - 1):
                no_u, no_v = coords[i], coords[i+1]
                distancia_km = ((no_u[0] - no_v[0])**2 + (no_u[1] - no_v[1])**2)**0.5 / 1000
                G.add_edge(no_u, no_v, weight=distancia_km)
    return G

def encontrar_no_mais_proximo(grafo, ponto_cidade):
    nos = list(grafo.nodes)
    if not nos: return (0, 0)
    cx, cy = ponto_cidade.x, ponto_cidade.y
    return min(nos, key=lambda no: (no[0] - cx)**2 + (no[1] - cy)**2)


# --- NOVO: FUNÇÃO DE EXTRAÇÃO COM MOTOR DE REDUNDÂNCIA E TELEMETRIA ---
def carregar_camada_com_telemetria(caminho_parquet, bbox_wgs84, nome_camada):
    """Carrega dados geográficos com validação contra falsos zeros e logs de execução."""
    log = {"camada": nome_camada, "status": "Não executado", "registros": 0, "detalhes": ""}
    
    if not os.path.exists(caminho_parquet):
        log["status"] = "❌ Arquivo não encontrado no repositório"
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log
        
    try:
        # Tentativa 1: Filtro nativo por BBox (Rápido, mas sujeito a falhas de metadados)
        gdf = gpd.read_parquet(caminho_parquet, bbox=bbox_wgs84)
        gdf = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf.set_crs(epsg=4326)
        
        log["status"] = "🟢 Sucesso (BBox Nativo)"
        log["registros"] = len(gdf)
        
        # INTERVENÇÃO CRÍTICA: Se o BBox nativo retornar 0 linhas, ativamos o Fallback Engine
        if len(gdf) == 0:
            log["status"] = "🟡 Acionado Fallback (Falso Zero Detectado)"
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            
            # Recorte espacial manual e preciso em memória RAM
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            
            log["registros"] = len(gdf)
            log["detalhes"] = f"Recuperado via varredura em memória RAM. Total filtrado: {len(gdf)} feições."
            
        return gdf, log
        
    except Exception as e:
        log["status"] = "🟠 Erro no BBox (Executando Fallback Total)"
        try:
            # Tentativa 2: Fallback total lendo o arquivo completo devido a falha de engine
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            
            log["registros"] = len(gdf)
            log["detalhes"] = f"Erro contornado. Dados filtrados manualmente. Origem do erro: {str(e)[:40]}"
            return gdf, log
        except Exception as e_critico:
            log["status"] = "🔴 Falha Crítica de Leitura"
            log["detalhes"] = f"Erro: {e_critico}"
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log


# --- 4. INTERFACE: SELETOR DE CONCESSIONÁRIAS REAL ---
st.sidebar.header("2.1. Controle de Concessionárias")

col_concess_alvo = 'concessionaria'
lista_concessionarias = sorted(malha[col_concess_alvo].unique())

concessionarias_selecionadas = st.sidebar.multiselect(
    "Ferrovias autorizadas para o traçado:",
    options=lista_concessionarias,
    # Pré-marca de forma inteligente as principais que você audita no estado
    default=[c for c in lista_concessionarias if "PAULISTA" in c or "MRS" in c or "CENTRO-ATLÂNTICA" in c],
    help="Remova as operadoras que você deseja bloquear no cálculo de menor caminho."
)

with st.sidebar.expander("📊 Ver Status Geral da Malha Nacional"):
    if 'status' in malha.columns:
        st.write(malha['status'].value_counts())


# --- 5. MOTOR DE CÁLCULO E ANÁLISE MULTICRITÉRIO ---
# --- DENTRO DO BOTÃO: FILTRAGEM GEOGRÁFICA DA REDE ---
if st.sidebar.button("Calcular Rota e Priorizar Trechos", use_container_width=True):
    if len(malha) == 1 and malha.geometry.iloc[0].coords[0] == (0,0):
        st.error("A base ferroviária está ausente.")
    else:
        with st.spinner("Filtrando malha concedida e executando análise multicritério..."):
            
            # Filtra os trilhos mantendo apenas as empresas autorizadas pelo analista
            malha_filtrada = malha.copy()
            if concessionarias_selecionadas:
                malha_filtrada = malha_filtrada[malha_filtrada[col_concess_alvo].isin(concessionarias_selecionadas)]
                
            # Cria o grafo com base estritamente no subconjunto escolhido
            malha_m = malha_filtrada.to_crs(epsg=5880)
            sedes_m = sedes_filtradas.to_crs(epsg=5880)
            
            ponto_origem = sedes_m[sedes_m['name_muni'] == muni_origem].geometry.values[0]
            ponto_destino = sedes_m[sedes_m['name_muni'] == muni_destino].geometry.values[0]
            
            G = extrair_grafo_ferroviario(malha_m)
            no_origem = encontrar_no_mais_proximo(G, ponto_origem)
            no_destino = encontrar_no_mais_proximo(G, ponto_destino)
            
            if no_origem == no_destino:
                st.session_state.dados_calculados = {"erro": "Origem e destino atraídos para o mesmo nó técnico."}
            else:
                try:
                    caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
                    rota_unificada = LineString(caminho_nos)
                    comprimento_total_km = sum(G[caminho_nos[i]][caminho_nos[i+1]]['weight'] for i in range(len(caminho_nos)-1))
                    
                    # Extração dos limites da rota em WGS84
                    gdf_rota_temp = gpd.GeoDataFrame(geometry=[rota_unificada], crs="EPSG:5880").to_crs(epsg=4326)
                    bbox_rota = gdf_rota_temp.geometry.iloc[0].bounds
                    margin = 0.08
                    
                    bbox_expandida = (
                        bbox_rota[0] - margin,
                        bbox_rota[1] - margin,
                        bbox_rota[2] + margin,
                        bbox_rota[3] + margin
                    )
                    
                    # EXECUÇÃO DAS CAMADAS COM COLETA DE LOGS DE DIAGNÓSTICO
                    ucs, log_uc = carregar_camada_com_telemetria("dados/unidades_conservacao.parquet", bbox_expandida, "Unidades de Conservação")
                    tis, log_ti = carregar_camada_com_telemetria("dados/terras_indigenas.parquet", bbox_expandida, "Terras Indígenas")
                    riscos, log_risco = carregar_camada_com_telemetria("dados/areas_risco.parquet", bbox_expandida, "Áreas de Risco (CPRM)")
                    rios, log_rio = carregar_camada_com_telemetria("dados/hidrografia.parquet", bbox_expandida, "Hidrografia (Rios)")
                    setores, log_setor = carregar_camada_com_telemetria("dados/setores_sp.parquet", bbox_expandida, "Setores Censitários (IBGE)")
                    
                    painel_logs = [log_uc, log_ti, log_risco, log_rio, log_setor]
                    
                    tam_trecho_metros = rota_unificada.length / num_trechos
                    listagem_trechos_diarios = []
                    
                    for i in range(num_trechos):
                        inicio_m = i * tam_trecho_metros
                        fim_m = (i + 1) * tam_trecho_metros
                        sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
                        
                        gdf_seg_m = gpd.GeoDataFrame(geometry=[sub_trecho_geom], crs="EPSG:5880")
                        buffer_wgs = gdf_seg_m.buffer(200).to_crs(epsg=4326).iloc[0]
                        
                        # Processamento espacial das intersecções reais
                        hit_ucs = ucs[ucs.intersects(buffer_wgs)]['nome_uc'].unique().tolist() if not ucs.empty else []
                        hit_tis = tis[tis.intersects(buffer_wgs)]['nome_ti'].unique().tolist() if not tis.empty else []
                        hit_riscos = riscos[riscos.intersects(buffer_wgs)]['classe_risco'].unique().tolist() if not riscos.empty else []
                        hit_rios = rios[rios.intersects(buffer_wgs)]['nome_rio'].unique().tolist() if not rios.empty else []
                        count_setores = len(setores[setores.intersects(buffer_wgs)]) if not setores.empty else 0
                        
                        # --- MATRIZ MULTICRITÉRIO (Notas de 0 a 10) ---
                        nota_ti = 10.0 if len(hit_tis) > 0 else 0.0
                        nota_uc = 8.0 if len(hit_ucs) > 0 else 0.0
                        nota_rio = 5.0 if len(hit_rios) > 0 else 0.0
                        
                        if any("MUITO ALTO" in r for r in hit_riscos): nota_risco = 10.0
                        elif any("ALTO" in r for r in hit_riscos): nota_risco = 6.0
                        else: nota_risco = 0.0
                            
                        if count_setores > 25: nota_setor = 8.0
                        elif count_setores > 8: nota_setor = 4.0
                        else: nota_setor = 0.0
                        
                        soma_pesos = w_ti + w_risco + w_uc + w_setores + w_rios
                        score_final = (
                            (nota_ti * w_ti) + (nota_risco * w_risco) + 
                            (nota_uc * w_uc) + (nota_setor * w_setores) + 
                            (nota_rio * w_rios)
                        ) / soma_pesos
                        
                        if score_final >= 4.5: criticidade, cor = "CRÍTICA", "red"
                        elif score_final >= 2.5: criticidade, cor = "ALTA", "orange"
                        elif score_final >= 0.8: criticidade, cor = "MÉDIA", "yellow"
                        else: criticidade, cor = "BAIXA", "blue"
                            
                        listagem_trechos_diarios.append({
                            'id_dia': f"Dia {i+1}",
                            'km_inicial': inicio_m / 1000,
                            'km_final': fim_m / 1000,
                            'extensao': sub_trecho_geom.length / 1000,
                            'criticidade': criticidade,
                            'score_num': score_final,
                            'cor_rgb': cor,
                            'interf_uc': ", ".join(hit_ucs) if hit_ucs else "Nenhuma",
                            'interf_ti': ", ".join(hit_tis) if hit_tis else "Nenhuma",
                            'interf_risco': ", ".join(hit_riscos) if hit_riscos else "Nenhum mapeado",
                            'interf_rios': ", ".join(hit_rios) if hit_rios else "Nenhum grande rio",
                            'interf_setores': f"{count_setores} setores urbanos cruzados",
                            'geometry': sub_trecho_geom
                        })
                        
                    gdf_cronograma = gpd.GeoDataFrame(listagem_trechos_diarios, crs="EPSG:5880")
                    gdf_cronograma_wgs84 = gdf_cronograma.to_crs(epsg=4326)
                    
                    st.session_state.dados_calculados = {
                        "muni_origem": muni_origem,
                        "muni_destino": muni_destino,
                        "uf_selecionada": uf_selecionada,
                        "comprimento_total_km": comprimento_total_km,
                        "num_trechos": num_trechos,
                        "gdf_cronograma_wgs84": gdf_cronograma_wgs84,
                        "nos_gerados": len(G.nodes),
                        "logs_diagnostico": painel_logs
                    }
                except nx.NetworkXNoPath:
                    st.session_state.dados_calculados = {"erro": f"Sem conexão ferroviária contínua entre {muni_origem} e {muni_destino}."}
                except Exception as e:
                    st.session_state.dados_calculados = {"erro": f"Erro no processamento espacial: {e}"}

# --- 6. EXIBIÇÃO EM PAINEL INTELIGENTE ---
if st.session_state.dados_calculados is not None:
    dados = st.session_state.dados_calculados
    if "erro" in dados:
        st.error(dados["erro"])
    else:
        st.subheader(f"📍 Rota Priorizada: {dados['muni_origem']} ➡️ {dados['muni_destino']} ({dados['uf_selecionada']})")
        st.success("Análise de criticidade baseada na ponderação de pesos atual recalculada!")
        
        col1, col2 = st.columns(2)
        col1.metric("Distância Total nos Trilhos", f"{dados['comprimento_total_km']:.2f} km")
        col2.metric("Média de Deslocamento Diário", f"{(dados['comprimento_total_km'] / dados['num_trechos']):.2f} km/dia")
        
        # --- NOVO: PAINEL DE TELEMETRIA VISÍVEL PARA O USUÁRIO ---
        if "logs_diagnostico" in dados:
            with st.expander("🛠️ Painel de Diagnóstico e Logs de Leitura Geográfica"):
                st.markdown("Verifique abaixo o comportamento de carregamento das camadas geográficas Parquet:")
                for log in dados["logs_diagnostico"]:
                    st.markdown(f"**🔹 Camada:** {log['camada']} | **Status:** {log['status']} | **Feições na Rota:** `{log['registros']}`")
                    if log["detalhes"]:
                        st.caption(f"↳ {log['detalhes']}")
        
        st.write("---")
        col_lista, col_mapa = st.columns([4, 5])
        
        with col_lista:
            st.write("### 🗓️ Matriz de Sensibilidade de Campo")
            gdf_wgs84 = dados['gdf_cronograma_wgs84']
            
            for idx, row in gdf_wgs84.iterrows():
                texto_trecho = f"**{row['id_dia']}:** km {row['km_inicial']:.1f} ao {row['km_final']:.1f} ({row['extensao']:.1f} km) — **Score: {row['score_num']:.2f}**"
                
                if row['criticidade'] == "CRÍTICA": st.error(f"🔴 {texto_trecho} — **CRÍTICO**")
                elif row['criticidade'] == "ALTA": st.warning(f"🟠 {texto_trecho} — **SENSÍVEL (ALTO)**")
                elif row['criticidade'] == "MÉDIA": st.info(f"🟡 {texto_trecho} — **MODERADO (MÉDIO)**")
                else: st.success(f"🔵 {texto_trecho} — **BAIXO IMPACTO**")
                
                with st.expander("Ver Intersecções Detectadas"):
                    st.write(f"⚠️ **Riscos Geológicos (CPRM):** {row['interf_risco']}")
                    st.write(f"🌳 **Unidades de Conservação:** {row['interf_uc']}")
                    st.write(f"🏹 **Terras Indígenas (Funai):** {row['interf_ti']}")
                    st.write(f"💧 **Corpos d'Água Principais:** {row['interf_rios']}")
                    st.write(f"👥 **Malha Censitária (IBGE):** {row['interf_setores']}")
                st.write("")
        
        with col_mapa:
            st.write("### 🗺️ Mapa Temático Dinâmico")
            centro_mapa = gdf_wgs84.unary_union.centroid
            m = folium.Map(location=[centro_mapa.y, centro_mapa.x], zoom_start=8, tiles="CartoDB positron")
            
            for idx, row in gdf_wgs84.iterrows():
                cor = row['cor_rgb']
                geo_json_features = folium.GeoJson(
                    row['geometry'].__geo_interface__,
                    style_function=lambda x, c=cor: {'color': c, 'weight': 6, 'opacity': 0.9}
                )
                
                popup_html = f"""
                <div style='font-family: Arial, sans-serif; width: 230px; font-size:12px;'>
                    <h4 style='margin:0 0 5px 0; color:{cor};'>{row['id_dia']} ({row['criticidade']})</h4>
                    <b>Score de Risco:</b> {row['score_num']:.2f}<br>
                    <b>Trecho:</b> km {row['km_inicial']:.1f} ao km {row['km_final']:.1f}<br>
                    <b>Risco CPRM:</b> {row['interf_risco']}<br>
                    <b>UCs:</b> {row['interf_uc']}<br>
                    <b>TIs:</b> {row['interf_ti']}<br>
                    <b>Rios:</b> {row['interf_rios']}<br>
                    <b>Censo IBGE:</b> {row['interf_setores']}
                </div>
                """
                folium.Popup(popup_html, max_width=250).add_to(geo_json_features)
                geo_json_features.add_to(m)
                
            st_folium(m, height=550, use_container_width=True)
