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
st.markdown("Análise multicritério interestadual com identificação de Alvos Críticos de 1 km para vistoria in loco.")

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

def carregar_camada_com_telemetria(caminho_parquet, bbox_wgs84, nome_camada):
    log = {"camada": nome_camada, "status": "Não executado", "registros": 0}
    if not os.path.exists(caminho_parquet):
        log["status"] = "⚠️ Arquivo opcional ausente"
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log
    try:
        gdf = gpd.read_parquet(caminho_parquet, bbox=bbox_wgs84)
        gdf = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf.set_crs(epsg=4326)
        log["status"] = "🟢 Sucesso (BBox Nativo)"
        log["registros"] = len(gdf)
        if len(gdf) == 0:
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            log["registros"] = len(gdf)
            log["status"] = "🟢 Sucesso (Mapeamento RAM)"
        return gdf, log
    except Exception:
        try:
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            log["registros"] = len(gdf)
            log["status"] = "🟢 Sucesso (Mapeamento RAM)"
            return gdf, log
        except Exception:
            log["status"] = "🔴 Falha Crítica"
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log


# --- 4. INTERFACE DO USUÁRIO ---
st.sidebar.header("1. Origem e Destino (Interestadual)")
lista_ufs = sorted(sedes['abbrev_state'].unique())

uf_origem = st.sidebar.selectbox("UF de Partida:", lista_ufs, index=lista_ufs.index("SP") if "SP" in lista_ufs else 0)
sedes_origem_df = sedes[sedes['abbrev_state'] == uf_origem].sort_values(by="name_muni")
muni_origem = st.sidebar.selectbox("Município de Partida:", sedes_origem_df['name_muni'].unique(), index=0)

uf_destino = st.sidebar.selectbox("UF de Destino:", lista_ufs, index=lista_ufs.index("SP") if "SP" in lista_ufs else 0)
sedes_destino_df = sedes[sedes['abbrev_state'] == uf_destino].sort_values(by="name_muni")
muni_destino = st.sidebar.selectbox("Município de Destino:", sedes_destino_df['name_muni'].unique(), index=min(1, len(sedes_destino_df)-1))

st.sidebar.header("2.1. Controle de Concessionárias")
if 'concessionaria' in malha.columns:
    col_concess_alvo = 'concessionaria'
    lista_concessionarias = sorted(malha[col_concess_alvo].unique())
    default_selecao = [c for c in lista_concessionarias if "PAULISTA" in c or "MRS" in c or "CENTRO" in c]
else:
    col_concess_alvo = None
    lista_concessionarias = []
    default_selecao = []

if col_concess_alvo:
    concessionarias_selecionadas = st.sidebar.multiselect(
        "Ferrovias autorizadas para o traçado:", options=lista_concessionarias, default=default_selecao
    )
else:
    concessionarias_selecionadas = None

st.sidebar.header("3. Cronograma")
num_trechos = st.sidebar.number_input("Quantidade de trechos a dividir:", min_value=1, value=3)

st.sidebar.header("⚙️ 4. Pesos de Criticidade (1 a 5)")
w_ti = st.sidebar.slider("🏹 Terras Indígenas", 1, 5, value=5)
w_risco = st.sidebar.slider("⚠️ Riscos Geológicos", 1, 5, value=4)
w_uc = st.sidebar.slider("🌳 Unidades de Conservação", 1, 5, value=4)
w_setores = st.sidebar.slider("👥 Adensamento / Censo", 1, 5, value=2)
w_rios = st.sidebar.slider("💧 Hidrografia / Rios", 1, 5, value=2)


# --- 5. MOTOR DE CÁLCULO E ANÁLISE MULTICRITÉRIO ---
if st.sidebar.button("Calcular Rota e Priorizar Trechos", use_container_width=True):
    if len(malha) == 1 and malha.geometry.iloc[0].coords[0] == (0,0):
        st.error("A base ferroviária está ausente.")
    else:
        with st.spinner("Traçando rota interestadual e calculando cruzamentos estruturais de precisão..."):
            
            malha_filtrada = malha.copy()
            if concessionarias_selecionadas and col_concess_alvo:
                malha_filtrada = malha_filtrada[malha_filtrada[col_concess_alvo].isin(concessionarias_selecionadas)]
                
            malha_m = malha_filtrada.to_crs(epsg=5880)
            sedes_origem_m = sedes_origem_df.to_crs(epsg=5880)
            sedes_destino_m = sedes_destino_df.to_crs(epsg=5880)
            
            ponto_origem = sedes_origem_m[sedes_origem_m['name_muni'] == muni_origem].geometry.values[0]
            ponto_destino = sedes_destino_m[sedes_destino_m['name_muni'] == muni_destino].geometry.values[0]
            
            G = extrair_grafo_ferroviario(malha_m)
            no_origem = encontrar_no_mais_proximo(G, ponto_origem)
            no_destino = encontrar_no_mais_proximo(G, ponto_destino)
            
            if no_origem == no_destino:
                st.error("Origem e destino atraídos para o mesmo nó técnico.")
            else:
                try:
                    caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
                    rota_unificada = LineString(caminho_nos)
                    comprimento_total_km = sum(G[caminho_nos[i]][caminho_nos[i+1]]['weight'] for i in range(len(caminho_nos)-1))
                    
                    gdf_rota_temp = gpd.GeoDataFrame(geometry=[rota_unificada], crs="EPSG:5880").to_crs(epsg=4326)
                    bbox_rota = gdf_rota_temp.geometry.iloc[0].bounds
                    margin = 0.08
                    bbox_expandida = (bbox_rota[0]-margin, bbox_rota[1]-margin, bbox_rota[2]+margin, bbox_rota[3]+margin)
                    
                    # Carregamento de dados de suporte
                    ucs, log_uc = carregar_camada_com_telemetria("dados/unidades_conservacao.parquet", bbox_expandida, "Unidades de Conservação")
                    tis, log_ti = carregar_camada_com_telemetria("dados/terras_indigenas.parquet", bbox_expandida, "Terras Indígenas")
                    riscos, log_risco = carregar_camada_com_telemetria("dados/areas_risco.parquet", bbox_expandida, "Áreas de Risco (CPRM)")
                    rios, log_rio = carregar_camada_com_telemetria("dados/hidrografia.parquet", bbox_expandida, "Hidrografia (Rios)")
                    setores, log_setor = carregar_camada_com_telemetria("dados/setores_sp.parquet", bbox_expandida, "Setores Censitários (IBGE)")
                    rodovias, log_rod = carregar_camada_com_telemetria("dados/rodovias.parquet", bbox_expandida, "Malha Rodoviária")
                    patios, log_pat = carregar_camada_com_telemetria("dados/patios_oficinas.parquet", bbox_expandida, "Pátios e Oficinas")
                    
                    painel_logs = [log_uc, log_ti, log_risco, log_rio, log_setor, log_rod, log_pat]
                    soma_pesos = w_ti + w_risco + w_uc + w_setores + w_rios
                    
                    tam_trecho_metros = rota_unificada.length / num_trechos
                    listagem_trechos_diarios = []
                    todos_os_top_micros = []
                    
                    for i in range(num_trechos):
                        inicio_m = i * tam_trecho_metros
                        fim_m = (i + 1) * tam_trecho_metros
                        sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
                        
                        gdf_seg_m = gpd.GeoDataFrame(geometry=[sub_trecho_geom], crs="EPSG:5880")
                        sub_trecho_wgs = gdf_seg_m.to_crs(epsg=4326).geometry.iloc[0]
                        buffer_wgs = gdf_seg_m.buffer(200).to_crs(epsg=4326).iloc[0]
                        
                        # Cruzamentos do Macro Trecho Diário
                        hit_ucs = ucs[ucs.intersects(buffer_wgs)]['nome_uc'].unique().tolist() if not ucs.empty else []
                        hit_tis = tis[tis.intersects(buffer_wgs)]['nome_ti'].unique().tolist() if not tis.empty else []
                        hit_riscos = riscos[riscos.intersects(buffer_wgs)]['classe_risco'].unique().tolist() if not riscos.empty else []
                        hit_rios = rios[rios.intersects(buffer_wgs)]['nome_rio'].unique().tolist() if not rios.empty else []
                        count_setores = len(setores[setores.intersects(buffer_wgs)]) if not setores.empty else 0
                        
                        hit_patios = patios[patios.intersects(buffer_wgs)] if not patios.empty else gpd.GeoDataFrame()
                        col_nome_patio = [c for c in hit_patios.columns if 'nome' in c or 'patio' in c or 'oficina' in c]
                        nomes_patios = hit_patios[col_nome_patio[0]].unique().tolist() if (not hit_patios.empty and col_nome_patio) else []
                        
                        # Pontos exatos de infraestrutura
                        list_pn_coords, list_pontes_coords = [], []
                        if not rodovias.empty:
                            rod_hits = rodovias[rodovias.intersects(sub_trecho_wgs)]
                            if not rod_hits.empty:
                                for g in rod_hits.intersection(sub_trecho_wgs):
                                    if g.geom_type == 'Point': list_pn_coords.append((g.y, g.x))
                                    elif g.geom_type == 'MultiPoint': list_pn_coords.extend([(p.y, p.x) for p in g.geoms])
                        if not rios.empty:
                            rio_hits = rios[rios.intersects(sub_trecho_wgs)]
                            if not rio_hits.empty:
                                for g in rio_hits.intersection(sub_trecho_wgs):
                                    if g.geom_type == 'Point': list_pontes_coords.append((g.y, g.x))
                                    elif g.geom_type == 'MultiPoint': list_pontes_coords.extend([(p.y, p.x) for p in g.geoms])
                        
                        nota_ti = 10.0 if len(hit_tis) > 0 else 0.0
                        nota_uc = 8.0 if len(hit_ucs) > 0 else 0.0
                        nota_rio = 5.0 if len(hit_rios) > 0 else 0.0
                        nota_risco = 10.0 if any("MUITO ALTO" in r for r in hit_riscos) else (6.0 if any("ALTO" in r for r in hit_riscos) else 0.0)
                        nota_setor = 8.0 if count_setores > 25 else (4.0 if count_setores > 8 else 0.0)
                        
                        score_macro = ((nota_ti * w_ti) + (nota_risco * w_risco) + (nota_uc * w_uc) + (nota_setor * w_setores) + (nota_rio * w_rios)) / soma_pesos
                        criticidade, cor = ("CRÍTICA", "red") if score_macro >= 4.5 else (("ALTA", "orange") if score_macro >= 2.5 else (("MÉDIA", "yellow") if score_macro >= 0.8 else ("BAIXA", "blue")))
                        
                        # Loop de fatiamento interno de 1 km
                        micro_start = inicio_m
                        micro_chunks_dia = []
                        
                        while micro_start < fim_m:
                            micro_end = min(micro_start + 1000.0, fim_m)
                            if (micro_end - micro_start) < 50.0: break
                            
                            micro_geom = substring(rota_unificada, micro_start, micro_end)
                            gdf_micro_m = gpd.GeoDataFrame(geometry=[micro_geom], crs="EPSG:5880")
                            m_buffer_wgs = gdf_micro_m.buffer(200).to_crs(epsg=4326).iloc[0]
                            
                            m_ucs = ucs[ucs.intersects(m_buffer_wgs)]['nome_uc'].unique().tolist() if not ucs.empty else []
                            m_tis = tis[tis.intersects(m_buffer_wgs)]['nome_ti'].unique().tolist() if not tis.empty else []
                            m_riscos = riscos[riscos.intersects(m_buffer_wgs)]['classe_risco'].unique().tolist() if not riscos.empty else []
                            m_rios = rios[rios.intersects(m_buffer_wgs)]['nome_rio'].unique().tolist() if not rios.empty else []
                            m_setores = len(setores[setores.intersects(m_buffer_wgs)]) if not setores.empty else 0
                            
                            m_n_ti = 10.0 if len(m_tis) > 0 else 0.0
                            m_n_uc = 8.0 if len(m_ucs) > 0 else 0.0
                            m_n_rio = 5.0 if len(m_rios) > 0 else 0.0
                            m_n_risco = 10.0 if any("MUITO ALTO" in r for r in m_riscos) else (6.0 if any("ALTO" in r for r in m_riscos) else 0.0)
                            m_n_setor = 8.0 if m_setores > 6 else (4.0 if m_setores > 2 else 0.0)
                            
                            score_micro = ((m_n_ti * w_ti) + (m_n_risco * w_risco) + (m_n_uc * w_uc) + (m_n_setor * w_setores) + (m_n_rio * w_rios)) / soma_pesos
                            
                            # --- CORREÇÃO CIRÚRGICA: Montagem dinâmica e segura do resumo de interferências ---
                            if m_ucs and m_riscos:
                                resumo = f"🌳 UC: {m_ucs[0][:15]}... | ⚠️ Risco: {m_riscos[0]}"
                            elif m_ucs:
                                resumo = f"🌳 UC: {m_ucs[0][:25]}..."
                            elif m_riscos:
                                resumo = f"⚠️ Risco CPRM: {m_riscos[0]}"
                            elif m_tis:
                                resumo = f"🏹 TI: {m_tis[0][:25]}..."
                            else:
                                resumo = "Baixa interferência socioambiental direta"
                            
                            micro_chunks_dia.append({
                                'id_dia': f"Dia {i+1}",
                                'km_inicial': micro_start / 1000,
                                'km_final': micro_end / 1000,
                                'score_num': score_micro,
                                'resumo_interf': resumo,
                                'geometry': micro_geom
                            })
                            micro_start += 1000.0
                        
                        top_5_do_dia = sorted(micro_chunks_dia, key=lambda x: x['score_num'], reverse=True)[:5]
                        todos_os_top_micros.extend(top_5_do_dia)
                        
                        listagem_trechos_diarios.append({
                            'id_dia': f"Dia {i+1}", 'km_inicial': inicio_m / 1000, 'km_final': fim_m / 1000, 'extensao': sub_trecho_geom.length / 1000,
                            'criticidade': criticidade, 'score_num': score_macro, 'cor_rgb': cor,
                            'interf_uc': ", ".join(hit_ucs) if hit_ucs else "Nenhuma",
                            'interf_ti': ", ".join(hit_tis) if hit_tis else "Nenhuma",
                            'interf_risco': ", ".join(hit_riscos) if hit_riscos else "Nenhum mapeado",
                            'interf_rios': ", ".join(hit_rios) if hit_rios else "Nenhum grande rio",
                            'interf_setores': f"{count_setores} setores urbanos cruzados",
                            'interf_patios': ", ".join(nomes_patios) if nomes_patios else "Nenhum pátio na faixa de domínio",
                            'pn_pontos': list_pn_coords, 'pontes_pontes': list_pontes_coords, 'geometry': sub_trecho_geom
                        })
                        
                    gdf_cronograma = gpd.GeoDataFrame(listagem_trechos_diarios, crs="EPSG:5880")
                    
                    # BLINDAGEM ADICIONAL: Definição clara da coluna geométrica ativa
                    gdf_top_micros = gpd.GeoDataFrame(todos_os_top_micros, geometry='geometry', crs="EPSG:5880")
                    
                    st.session_state.dados_calculados = {
                        "muni_origem": muni_origem, "muni_destino": muni_destino,
                        "uf_origem": uf_origem, "uf_destino": uf_destino,
                        "comprimento_total_km": comprimento_total_km, "num_trechos": num_trechos,
                        "gdf_cronograma_wgs84": gdf_cronograma.to_crs(epsg=4326),
                        "gdf_top_micros_wgs84": gdf_top_micros.to_crs(epsg=4326),
                        "rios_wgs84": rios if not rios.empty else None,
                        "ucs_wgs84": ucs if not ucs.empty else None,
                        "tis_wgs84": tis if not tis.empty else None,
                        "riscos_wgs84": riscos if not riscos.empty else None,
                        "rodovias_wgs84": rodovias if not rodovias.empty else None,
                        "setores_wgs84": setores if not setores.empty else None,
                        "patios_wgs84": patios if not patios.empty else None,
                        "logs_diagnostico": painel_logs
                    }
                except nx.NetworkXNoPath:
                    st.error("Sem conexão ferroviária contínua instalada entre as duas cidades.")

# --- 6. EXIBIÇÃO EM PAINEL INTELIGENTE ---
if st.session_state.dados_calculados is not None:
    dados = st.session_state.dados_calculados
    if "erro" in dados: st.error(dados["erro"])
    else:
        st.subheader(f"📍 Rota Priorizada: {dados['muni_origem']} ({dados['uf_origem']}) ➡️ {dados['muni_destino']} ({dados['uf_destino']})")
        st.success("Análise de hotspots de 1 km concluída com sucesso sobre a malha de grafos!")
        
        col1, col2 = st.columns(2)
        col1.metric("Distância Total nos Trilhos", f"{dados['comprimento_total_km']:.2f} km")
        col2.metric("Média de Deslocamento Diário", f"{(dados['comprimento_total_km'] / dados['num_trechos']):.2f} km/dia")
        
        if "logs_diagnostico" in dados:
            with st.expander("🛠️ Painel de Diagnóstico e Logs de Leitura Geográfica"):
                st.markdown("Verifique abaixo o comportamento de carregamento das camadas geográficas Parquet:")
                for log in dados["logs_diagnostico"]:
                    st.markdown(f"**🔹 Camada:** {log['camada']} | **Status:** {log['status']} | **Feições na Rota:** `{log['registros']}`")
        
        st.write("---")
        col_lista, col_mapa = st.columns([4, 5])
        
        with col_lista:
            st.write("### 🗓️ Matriz de Sensibilidade e Alvos de Fiscalização")
            gdf_wgs84 = dados['gdf_cronograma_wgs84']
            
            # BLINDAGEM CONTRA CACHE VELHO: Captura de forma segura a nova camada usando .get()
            gdf_micros_wgs84 = dados.get('gdf_top_micros_wgs84', None)
            
            for idx, row in gdf_wgs84.iterrows():
                texto_trecho = f"**{row['id_dia']}:** km {row['km_inicial']:.1f} ao {row['km_final']:.1f} ({row['extensao']:.1f} km) — **Score: {row['score_num']:.2f}**"
                if row['criticidade'] == "CRÍTICA": st.error(f"🔴 {texto_trecho}")
                elif row['criticidade'] == "ALTA": st.warning(f"🟠 {texto_trecho}")
                elif row['criticidade'] == "MÉDIA": st.info(f"🟡 {texto_trecho}")
                else: st.success(f"🔵 {texto_trecho}")
                
                with st.expander("Ver Cruzamentos e Hotspots de 1 km (Alvos In Loco)"):
                    # Executa a listagem fina se os dados novos existirem em memória
                    if gdf_micros_wgs84 is not None and not gdf_micros_wgs84.empty:
                        st.markdown("🎯 **Top 5 Trechos de 1 km mais Sensíveis para Vistoria Prática:**")
                        micros_do_dia = gdf_micros_wgs84[gdf_micros_wgs84['id_dia'] == row['id_dia']]
                        for m_idx, m_row in micros_do_dia.iterrows():
                            st.markdown(f"   • 📍 **km {m_row['km_inicial']:.1f} ao {m_row['km_final']:.1f}** — Score: `{m_row['score_num']:.2f}` ({m_row['resumo_interf']})")
                    else:
                        st.caption("⚠️ Alvos de 1km indisponíveis na memória residual. Clique em 'Calcular Rota' para gerar os novos hotspots.")
                    
                    st.write("---")
                    st.markdown(f"🛣️ **Passagens de Nível:** `{len(row['pn_pontos'])}` | 🌉 **Pontes sobre Rios:** `{len(row['pontes_pontes'])}`")
                    st.caption(f"⚠️ **CPRM:** {row['interf_risco']} | 🌳 **UCs:** {row['interf_uc']}")
                st.write("")
        
        with col_mapa:
            st.write("### 🗺️ Mapa Temático Dinâmico Avançado")
            centro_mapa = gdf_wgs84.unary_union.centroid
            m = folium.Map(location=[centro_mapa.y, centro_mapa.x], zoom_start=8, tiles="CartoDB positron")
            
            m.add_child(folium.LatLngPopup())
            
            if dados.get("rios_wgs84") is not None and not dados["rios_wgs84"].empty:
                folium.GeoJson(dados["rios_wgs84"], name="💧 Hidrografia (Parquet)", show=True, style_function=lambda x: {'color': '#1d70b8', 'weight': 2}).add_to(m)
            if dados.get("ucs_wgs84") is not None and not dados["ucs_wgs84"].empty:
                folium.GeoJson(dados["ucs_wgs84"], name="🌳 Unidades de Conservação", show=False, style_function=lambda x: {'color': 'green', 'fillColor': 'green', 'fillOpacity': 0.1, 'weight': 1}).add_to(m)
            if dados.get("riscos_wgs84") is not None and not dados["riscos_wgs84"].empty:
                folium.GeoJson(dados["riscos_wgs84"], name="⚠️ Áreas de Risco (CPRM)", show=False, style_function=lambda x: {'color': 'orange', 'fillColor': 'yellow', 'fillOpacity': 0.1, 'weight': 1}).add_to(m)
            if dados.get("rodovias_wgs84") is not None and not dados["rodovias_wgs84"].empty:
                folium.GeoJson(dados["rodovias_wgs84"], name="🛣️ Malha Rodoviária", show=False, style_function=lambda x: {'color': '#707070', 'weight': 1.2}).add_to(m)

            # 1. Linhas de base por dia
            for idx, row in gdf_wgs84.iterrows():
                cor = row['cor_rgb']
                folium.GeoJson(
                    row['geometry'].__geo_interface__, name=f"🛤️ {row['id_dia']}",
                    style_function=lambda x, c=cor: {'color': c, 'weight': 5, 'opacity': 0.8}
                ).add_to(m)
                
                for pt in row['pn_pontos']:
                    folium.CircleMarker(location=pt, radius=4, color='black', fill=True, fill_color='orange', popup="🛣️ Passagem de Nível").add_to(m)
                for pt_rio in row['pontes_pontes']:
                    folium.CircleMarker(location=pt_rio, radius=4, color='darkblue', fill=True, fill_color='cyan', popup="🌉 Ponte Ferroviária").add_to(m)
            
            # 2. BLINDAGEM DE EXIBIÇÃO: Desenha os alvos neon apenas se presentes
            if gdf_micros_wgs84 is not None and not gdf_micros_wgs84.empty:
                folium.GeoJson(
                    gdf_micros_wgs84,
                    name="🎯 Alvos Críticos de Vistoria (1 km)",
                    show=True,
                    style_function=lambda x: {
                        'color': '#ff007f',
                        'weight': 10,
                        'opacity': 0.95
                    },
                    tooltip=folium.GeoJsonTooltip(fields=['id_dia', 'km_inicial', 'km_final', 'score_num'], aliases=['Dia: ', 'km Inicial: ', 'km Final: ', 'Score do Alvo: '])
                ).add_to(m)
            
            folium.LayerControl(position='topright', collapsed=False).add_to(m)
            st_folium(m, height=580, use_container_width=True)
