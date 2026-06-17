import streamlit as st
import geopandas as gpd
import geobr
import networkx as nx
from shapely.ops import substring, linemerge, unary_union
from shapely.geometry import LineString, MultiLineString

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide", 
    page_title="Planejador Nacional de Vistoria Ferroviária",
    page_icon="🚊"
)

st.title("🚊 Planejador Nacional de Vistoria Ferroviária (Rede/Grafos)")
st.markdown("Ferramenta automatizada para traçado de rotas sobre trilhos e divisão de trechos operacionais diários.")

# --- 1. CARREGAMENTO DOS DADOS NACIONAIS (COM CACHE) ---
@st.cache_data(show_spinner=False)
def carregar_bases_nacionais():
    """
    Baixa e carrega as bases oficiais do IBGE/ANTT via biblioteca geobr.
    - read_railway(): Malha ferroviária federal completa.
    - read_municipal_seat(): Coordenadas (pontos) das sedes de todos os municípios.
    """
    malha_ferroviaria = geobr.read_railway()
    sedes_municipios = geobr.read_municipal_seat()
    return malha_ferroviaria, sedes_municipios

with st.spinner("Carregando bases geográficas nacionais do IBGE... (Pode demorar um pouco na primeira execução)"):
    malha, sedes = carregar_bases_nacionais()


# --- 2. FUNÇÕES AUXILIARES PARA PROCESSAMENTO DE REDE (GRAFOS) ---
def extrair_grafo_ferroviario(gdf_ferrovia):
    """
    Transforma as linhas do GeoDataFrame ferroviário em um Grafo do NetworkX.
    Cada extremidade de linha vira um nó (x, y) e o traçado vira uma aresta com peso (km).
    """
    G = nx.Graph()
    
    for idx, row in gdf_ferrovia.iterrows():
        geom = row.geometry
        if geom.geom_type == 'LineString':
            linhas = [geom]
        elif geom.geom_type == 'MultiLineString':
            linhas = geom.geoms
        else:
            continue
            
        for linha in list(linhas):
            coords = list(linha.coords)
            no_inicial = coords[0]   # Coordenada XY de início
            no_final = coords[-1]    # Coordenada XY de fim
            
            # O comprimento (length) estará em metros se o CRS estiver projetado
            distancia_km = linha.length / 1000  
            
            # Adiciona a aresta salvando a geometria original para reconstrução posterior
            G.add_edge(no_inicial, no_final, weight=distancia_km, geometry=linha)
            
    return G

def encontrar_no_mais_proximo(grafo, ponto_cidade):
    """
    Encontra o nó da malha ferroviária mais próximo da sede do município selecionado.
    """
    nos = list(grafo.nodes)
    no_proximo = min(nos, key=lambda no: ponto_cidade.distance(LineString([ponto_cidade, no])))
    return no_proximo


# --- 3. INTERFACE DO USUÁRIO (SIDEBAR) ---
st.sidebar.header("1. Seleção de Região")

# Lista de UFs únicas da base
lista_ufs = sorted(sedes['abbrev_state'].unique())
uf_selecionada = st.sidebar.selectbox(
    "Selecione a UF de atuação:", 
    lista_ufs, 
    index=lista_ufs.index("SP") if "SP" in lista_ufs else 0
)

# Filtra os municípios da UF escolhida
sedes_filtradas = sedes[sedes['abbrev_state'] == uf_selecionada].sort_values(by="name_muni")
lista_municipios = sedes_filtradas['name_muni'].unique()

st.sidebar.header("2. Rota da Viagem")
muni_origem = st.sidebar.selectbox("Município de Partida:", lista_municipios)
# Evita que o destino seja igual à origem na listagem
muni_destino = st.sidebar.selectbox("Município de Destino:", [m for m in lista_municipios if m != muni_origem])

st.sidebar.header("3. Cronograma")
datas = st.sidebar.date_input("Período da Vistoria:", [])

# Define a quantidade de trechos (padrão: 1 por dia de trabalho)
if len(datas) == 2:
    data_ini, data_fim = datas
    dias_trabalho = (data_fim - data_ini).days + 1
    
    num_trechos = st.sidebar.number_input(
        "Quantidade de trechos a dividir:", 
        min_value=1, 
        value=dias_trabalho, 
        help="Por padrão, adota-se 1 trecho por dia de trabalho."
    )
else:
    num_trechos = st.sidebar.number_input("Quantidade de trechos a dividir:", min_value=1, value=5)
    st.sidebar.warning("Selecione a data de início e término para sincronizar com os dias de trabalho.")


# --- 4. PROCESSAMENTO DA ROTA E CRONOGRAMA DIÁRIO ---
if st.sidebar.button("Calcular Rota e Dividir Trechos", use_container_width=True):
    st.subheader(f"📍 Planejamento Estruturado: {muni_origem} ➡️ {muni_destino} ({uf_selecionada})")
    
    # Projeta as bases para metros usando SIRGAS 2000 / Policônica (EPSG:5880), ideal para o Brasil
    with st.spinner("Reprojetando coordenadas para cálculo métrico de precisão..."):
        malha_m = malha.to_crs(epsg=5880)
        sedes_m = sedes_filtradas.to_crs(epsg=5880)
    
    # Resgata os pontos geométricos projetados das sedes de origem e destino
    ponto_origem = sedes_m[sedes_m['name_muni'] == muni_origem].geometry.values[0]
    ponto_destino = sedes_m[sedes_m['name_muni'] == muni_destino].geometry.values[0]
    
    with st.spinner("Construindo rede lógica de grafos da malha ferroviária..."):
        G = extrair_grafo_ferroviario(malha_m)
        
        # Faz o "snapping" (atração) das cidades para os nós de trilho mais próximos
        no_origem = encontrar_no_mais_proximo(G, ponto_origem)
        no_destino = encontrar_no_mais_proximo(G, ponto_destino)
    
    try:
        # Encontra o caminho mais curto sobre os trilhos (Algoritmo de Dijkstra)
        caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
        
        # Reconstrói as geometrias das linhas do caminho encontrado
        lista_linhas = []
        comprimento_total_km = 0
        for u, v in zip(caminho_nos[:-1], caminho_nos[1:]):
            dados_aresta = G[u][v]
            lista_linhas.append(dados_aresta['geometry'])
            comprimento_total_km += dados_aresta['weight']
            
        # Une os segmentos de linha em uma única geometria contínua
        rota_unificada = unary_union(lista_linhas)
        if rota_unificada.geom_type == 'MultiLineString':
            rota_unificada = linemerge(rota_unificada)
            
        st.success("Rota real mapeada com sucesso sobre os trilhos!")
        
        # Exibição de Métricas Gerais
        col1, col2 = st.columns(2)
        col1.metric("Distância Total nos Trilhos", f"{comprimento_total_km:.2f} km")
        col2.metric("Média Diária de Vistoria", f"{(comprimento_total_km / num_trechos):.2f} km/dia")
        
        # --- 5. FATIAMENTO GEOMÉTRICO (DISTRIBUIÇÃO DIÁRIA) ---
        st.write("---")
        st.write(f"### 🗓️ Cronograma Sugerido ({num_trechos} Dias Operacionais):")
        
        comprimento_total_metros = rota_unificada.length
        tam_trecho_metros = comprimento_total_metros / num_trechos
        
        for i in range(num_trechos):
            inicio_m = i * tam_trecho_metros
            fim_m = (i + 1) * tam_trecho_metros
            
            # Corta o LineString no intervalo exato de metros usando substring do Shapely
            sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
            
            km_inicial = inicio_m / 1000
            km_final = fim_m / 1000
            extensao_dia = (fim_m - inicio_m) / 1000
            
            # Mensagem de saída estruturada para o planejamento
            st.write(
                f"• **Dia {i+1}:** Início no **km {km_inicial:.1f}** ➡️ Término no **km {km_final:.1f}** "
                f"(Extensão do trecho: `{extensao_dia:.1f} km`)"
            )
            
            # Nota técnica: A variável 'sub_trecho_geom' armazena a geometria exata do dia, 
            # pronta para ser plotada em mapas ou usada em cruzamentos espaciais de risco.
            
    except nx.NetworkXNoPath:
        st.error(
            f"❌ Não foi encontrada uma conexão ferroviária contínua na base de dados entre "
            f"**{muni_origem}** e **{muni_destino}**. Verifique se os trechos pertencem à mesma malha física."
        )
    except Exception as e:
        st.error(f"Erro inesperado durante o processamento: {e}")
