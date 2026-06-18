```markdown
# 🚊 ViaPrev: Planejador Nacional de Vistoria Ferroviária com Matriz de Risco

Este repositório hospeda um **SAD (Sistema de Apoio à Decisão)** geoespacial e logístico desenvolvido em Python e implantado via Streamlit Cloud. O objetivo principal do aplicativo é automatizar o traçado de rotas ferroviárias contínuas em nível nacional, segmentar o cronograma de deslocamento das equipes de fiscalização e aplicar modelos de **Análise Multicritério (AHP/WLC)** para apontar instantaneamente os trechos de maior vulnerabilidade e sensibilidade socioambiental (*Hotspots*).

---

## 🚀 Funcionalidades Principais

* **Roteirização por Grafos Topológicos:** Conexão matemática precisa através da biblioteca `NetworkX` que une os trilhos federais de ponta a ponta, calculando o algoritmo de menor caminho (`shortest_path`) sem riscos de desconexão por simplificação vetorial destrutiva.
* **Filtro Comercial por Concessionária (Base PNV):** Permite isolar ou combinar malhas concedidas (ex: Rumo Malha Paulista, MRS Logística, FCA), recalculando o grafo e bloqueando dinamicamente trechos operados por empresas restritas na vistoria.
* **Planejador de Viagem Interestadual:** Seletores independentes de Unidade da Federação (UF) e municípios de origem e destino, permitindo rotas complexas que cruzam as fronteiras estaduais brasileiras.
* **Divisão Automatizada de Cronograma (Macro Trechos):** Fatiamento preciso da linha unificada da rota na quantidade de dias ou equipes estipuladas pelo analista.
* **Detector de Hotspots de 1 km (Micro Trechos):** Varredura interna em memória RAM que quebra cada macro trecho em segmentos exatos de 1 km, isolando e listando os **5 pontos mais críticos do dia** com extração de coordenadas nativas (Latitude e Longitude do início e fim do alvo).
* **Cruzamento Logístico e de Infraestrutura (Pontes e PNs):** Intersecção matricial em tempo real que mapeia e plota no mapa a localização geométrica exata de **Passagens de Nível** (cruzamento com rodovias) e **Pontes Ferroviárias** (cruzamento com corpos d'água principais).
* **Mesa de Luz para Auditoria (Visual Layer Control):** Painel interativo flutuante no mapa que permite ligar/desligar de forma independente as camadas brutas de polígonos e linhas de restrição para validação visual contra o mapa base.
* **Captura de Coordenadas em Campo:** Integração do plugin `LatLngPopup` que exibe em tela o par de coordenadas decimal exato de qualquer ponto clicado no mapa para fins de cópia direta.

---

## 📐 Premissas Metodológicas e Matriz de Risco

A classificação de criticidade socioambiental do planejador adota o método de **Combinação Linear Ponderada (Análise Multicritério - WLC)**. 

### 1. Faixa de Domínio (Buffer Espacial)
Todas as intersecções de vulnerabilidade são calculadas gerando uma zona de amortecimento (buffer geográfico) de **200 metros** de raio em torno do eixo central dos trilhos.

### 2. Pesos e Notas Estipulados
O sistema cruza as feições geográficas dentro do buffer atribuindo notas fixas de sensibilidade ($0.0$ a $10.0$) multiplicadas pelos pesos dinâmicos ($1$ a $5$) regulados pelo analista na interface lateral do sistema:

| Critério Socioambiental | Nota Padrão (Se Houver Intersecção) | Peso Padrão | Canal de Origem |
| :--- | :---: | :---: | :--- |
| **🏹 Terras Indígenas (TI)** | $10.0$ | `5` | FUNAI |
| **⚠️ Áreas de Risco Geológico** | $10.0$ (Muito Alto) / $6.0$ (Alto) | `4` | SGB / CPRM |
| **🌳 Unidades de Conservação (UC)** | $8.0$ | `4` | MMA / ICMBio |
| **👥 Adensamento Urbano (Censo)** | $8.0$ ($>25$ setores) / $4.0$ ($>8$ setores) | `2` | IBGE |
| **💧 Hidrografia (Rios Principais)**| $5.0$ | `2` | ANA / IBGE |

### 3. Equação do Score Final
O cálculo do índice de risco final de cada segmento linear é dado por:

$$Score = \frac{\sum (Nota_i \times Peso_i)}{\sum Peso_i}$$

Os resultados são classificados em 4 faixas rigorosas de priorização de campo:
* 🔴 **CRÍTICA:** $Score \ge 4.5$
* 🟠 **ALTA:** $Score \ge 2.5$
* 🟡 **MÉDIA:** $Score \ge 0.8$
* 🔵 **BAIXA:** $Score < 0.8$

---

## 🗄️ Estrutura do Repositório no GitHub

O repositório está estruturado de forma modular, separando a aplicação em produção, o banco de dados otimizado e os scripts de processamento:

```text
.
├── .streamlit/
│   └── config.toml                     # Configurações de interface e tema visual do painel
├── dados/                              # Banco de dados otimizado no formato nativo GeoParquet
│   ├── malha_ferroviaria.parquet       # Eixos de trilhos nacionais estruturados para grafos (12.73 MB)
│   ├── unidades_conservacao.parquet    # Polígonos de UCs federais e estaduais mapeadas
│   ├── terras_indigenas.parquet        # Polígonos de áreas demarcadas e homologadas (Funai)
│   ├── areas_risco.parquet             # Setores de risco a deslizamento e inundação (SGB/CPRM)
│   ├── hidrografia.parquet             # Eixos de drenagem e grandes rios de intersecção
│   ├── setores_sp.parquet              # Polígonos de densidade demográfica urbana (IBGE)
│   ├── rodovias.parquet                # Malha rodoviária integrada (cruzamentos de PNs)
│   └── patios_oficinas.parquet         # Pontos estratégicos de suporte técnico e pátios operacionais
├── processar_dados/                    # Módulos de ETL: Scripts de engenharia e limpeza de dados
│   ├── processar_ferrovias.py          # Harmonização, tratamento de strings e codificação PNV
│   ├── processar_hidrografia.py        # Otimização e indexação espacial da rede hídrica
│   ├── processar_patios.py             # Filtro e estruturação de pontos de apoio de pátios
│   ├── processar_perigo_sgb.py         # Padronização de classes de criticidade de risco do SGB
│   ├── processar_rodovias_SP.py        # Tratamento da malha rodoviária do estado de São Paulo
│   ├── processar_rodovias_federais.py  # Tratamento das diretrizes de rodovias federais (BRs)
│   ├── processar_setores_sp.py         # Filtro de alta densidade demográfica por km²
│   ├── processar_terras_indigenas.py   # Dissolve e simplificação de polígonos da Funai
│   └── processar_unidades_conservacao.py # Estruturação de restrições por grau de proteção
├── .gitignore                          # Restrição de subida de arquivos brutos/temporários (.zip, .shp)
├── packages.txt                        # Dependências a nível de S.O. para o container Linux (GDAL, PROJ)
├── requirements.txt                    # Dependências de bibliotecas Python para instalação via pip
└── vistorias.py                        # Script principal da aplicação (Interface Streamlit e Motores)

```

---

## ⚙️ Fluxo de Engenharia de Dados (ETL Layer)

Para manter a aplicação responsiva rodando sob os limites de hardware do Streamlit Community Cloud, todas as bases cartográficas brutas do governo federal passam por uma triagem e otimização severa na pasta `processar_dados/` antes de irem para produção:

1. **Redução de Atributos (Drop Columns):** São removidas colunas alfanuméricas redundantes de metadados textuais pesados, mantendo apenas identificadores unívocos (ex: `nome_uc`, `classe_risco`, `concessionaria`).
2. **Padronização Categórica:** Limpeza de strings, remoção de caracteres especiais e conversão de nomes de operadoras para strings limpas combinadas com as diretrizes do **PNV (Plano Nacional de Viação)** (ex: `codigo_pnv` como *EF-116*).
3. **Conversão Binária para GeoParquet:** Os arquivos brutos em Shapefiles e vetores pesados são comprimidos e salvos na pasta `dados/` no formato colunar `.parquet`. O arquivo de ferrovias, por exemplo, consolida-se em **12.73 MB**, mantendo todas as coordenadas milimétricas originais intactas para não quebrar a integridade topológica dos nós do grafo.

```
