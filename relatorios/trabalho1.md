# Relatório Técnico: Implementação de Stream de Vídeo com Raw Sockets
**Disciplina:** MC833
**Aluno:** Raphael Salles Vitor de Souza
**RA:** 223641

---

## 1. Definição do Protocolo e Diagrama de Sequência

A comunicação foi construída utilizando a pilha de protocolos **IPv4 + UDP + RTP** montada manualmente via Raw Sockets. 

* **Camada de Rede (IPv4):** Escolhida para o roteamento dos pacotes entre o servidor e o cliente.
* **Camada de Transporte (UDP):** O UDP foi escolhido pela ausência de *handshake* e retransmissão, características fundamentais para streaming de vídeo em tempo real, onde a velocidade é priorizada em detrimento da entrega garantida.
* **Camada de Aplicação/Transporte Real-Time (RTP):** Adicionado como *payload* do UDP para lidar com as deficiências do protocolo subjacente.

### Diagrama de Sequência (Interação Cliente-Servidor)
```text
Cliente (10.0.2.2)                                Servidor (10.0.1.2)
       |                                                 |
       | ------ [IP][UDP][Dados: "catalog"] -----------> |
       |                                                 |
       | <----- [IP][UDP][Dados: "Lista de Vídeos"] ---- |
       |                                                 |
       | ------ [IP][UDP][Dados: "stream video1.ts"] --> |
       |                                                 |
       | <----- [IP][UDP][RTP][Vídeo Chunk 1] ---------- |
       | <----- [IP][UDP][RTP][Vídeo Chunk 2] ---------- |
       | <----- [IP][UDP][RTP][Vídeo Chunk N] ---------- |
       |                                                 |
```

### Justificativa do Protocolo
A comunicação foi estruturada utilizando a pilha **IPv4 + UDP + RTP**.

* **IPv4 (Camada de Rede):** Responsável pelo roteamento e endereçamento dos pacotes através da rede virtual.
* **UDP (Camada de Transporte):** Escolhido por ser um protocolo não orientado à conexão, sem *handshake* e sem retransmissão. Para streaming de vídeo em tempo real, a velocidade e a entrega contínua são prioridades absolutas. O uso do TCP causaria travamentos indesejados (*buffering*) em caso de perda de pacotes.
* **RTP (Real-time Transport Protocol):** Encapsulado como *payload* do UDP para compensar a não-confiabilidade do transporte subjacente, fornecendo a inteligência necessária para a reconstrução contínua da mídia.

### Justificativa dos Campos Escolhidos (Cabeçalho RTP)
O cabeçalho RTP obrigatório de 12 bytes foi construído focando nos parâmetros mínimos vitais para o streaming:

* **Payload Type (PT):** Definido com o valor numérico **33**, que é o identificador padrão da IANA para o formato de transporte de mídia MPEG-TS.
* **Sequence Number (2 bytes):** Contador cíclico (0 a 65535) incrementado a cada pacote enviado pelo servidor. É o mecanismo que permite ao cliente identificar a perda de datagramas na rede ou detectar pacotes que chegaram fora de ordem, viabilizando a implementação futura de um *Jitter Buffer*.
* **Timestamp (4 bytes):** Carrega a marca de tempo contínua da amostragem do vídeo. É o campo responsável por ditar o ritmo de exibição no reprodutor (player), garantindo a reprodução na taxa de quadros (FPS) correta e a manutenção do *lip-sync* (sincronia de áudio e vídeo).
* **SSRC (4 bytes):** Identificador aleatório de sincronização, garantindo que o cliente saiba exatamente de qual fonte o stream está vindo.


## 2. Catálogo de Vídeos do Servidor

Para a homologação do servidor e testes de streaming na arquitetura implementada, foram disponibilizados três vídeos no formato MPEG Transport Stream (`.ts`), padronizados para o transporte contínuo de mídia. Os videos estão armazenados dentro da pasta *servidor/videos* no ambiente e seguem uma nomencltura simples:

1. `video1.ts`
2. `video2.ts`
3. `video3.ts`

Os videos foram retirados do site: [https://filesamples.com/formats/ts](https://filesamples.com/formats/ts)

---

## 3. Estrutura dos Cabeçalhos

A arquitetura de encapsulamento (boneca russa) segue uma sobreposição estrita das camadas de rede, transporte e aplicação. O tamanho total reservado para os cabeçalhos em cada pacote de vídeo gerado pelo servidor é de **40 bytes** (excluindo a camada de enlace Ethernet). 

Abaixo está a ilustração detalhada da alocação de bytes e dos campos enviados entre o servidor e o cliente:

| Camada / Protocolo | Tamanho Reservado | Estrutura de Campos |
| :--- | :--- | :--- |
| **Rede (IPv4)** | 20 bytes | Versão e IHL (1 byte), Type of Service (1 byte), Total Length (2 bytes), Identification (2 bytes), Flags e Fragment Offset (2 bytes), Time to Live (1 byte), Protocolo (1 byte - UDP), IP Header Checksum (2 bytes), Endereço IP de Origem (4 bytes), Endereço IP de Destino (4 bytes). |
| **Transporte (UDP)** | 8 bytes | Porta de Origem (2 bytes), Porta de Destino (2 bytes), Length (2 bytes), Checksum (2 bytes). |
| **Aplicação (RTP)** | 12 bytes | Versão/Padding/Ext/CC (1 byte), Marker e Payload Type (1 byte), Sequence Number (2 bytes), Timestamp (4 bytes), SSRC Identifier (4 bytes). |

## 4. Quantidade de Bytes Reservados para Dados

Foram reservados exatos **1316 bytes** exclusivamente para os dados (payload do vídeo bruto) em cada pacote enviado pelo servidor.

**Justificativa Arquitetural:**
O formato de transporte MPEG-TS (`.ts`), largamente utilizado em broadcast e streaming, agrupa dados em blocos atômicos e indivisíveis de exatos **188 bytes**. O valor de 1316 bytes não é arbitrário; ele corresponde à alocação perfeita de **7 blocos MPEG-TS completos** ($188 \times 7 = 1316$).

Somando os dados estritos (1316 bytes) com o *overhead* exigido pelos cabeçalhos de transporte e rede — RTP (12 bytes) + UDP (8 bytes) + IP (20 bytes) — obtemos um pacote IPv4 de **1356 bytes**. Essa engenharia de empacotamento foi estrategicamente dimensionada para ser inferior ao MTU (*Maximum Transmission Unit*) padrão das redes Ethernet (1500 bytes). Isso assegura que o pacote viaje inteiro pela rede, evitando a fragmentação na camada IP, o que fatalmente degradaria a performance do streaming de vídeo em tempo real.

## 5. Quantidade de Pacotes Necessária por Frame

Para calcular a quantidade atômica de pacotes de rede (UDP/RTP) necessários para transportar um único quadro (frame) de vídeo, utilizamos a relação entre o *Bitrate* total (taxa de bits do arquivo), a taxa de quadros (FPS) e o tamanho do nosso *payload* de transporte de dados (1316 bytes estritos de vídeo por pacote).

A modelagem matemática aplicada foi:
$$Tamanho\ do\ Frame\ (Bytes) = \frac{Bitrate\ (bps)}{8 \times FPS}$$
$$Pacotes\ por\ Frame = \lceil \frac{Tamanho\ do\ Frame}{1316} \rceil$$

*(Nota: O operador teto $\lceil \rceil$ foi aplicado pois a fragmentação da rede exige o envio de um pacote inteiro adicional caso haja sobra de bytes do quadro).*

Aplicando a análise aos 3 arquivos de amostragem (`.ts`) do laboratório:

**Análise do Vídeo 1 (`video1.ts`):**
* **FPS:** 23.976 quadros/s
* **Bitrate Médio:** 2.065.000 bps (2065 kb/s)
* **Cálculo (Tamanho):** $\frac{2065000}{8 \times 23.976} = 10765,97\ Bytes/frame$
* **Pacotes por Frame:** $\lceil \frac{10765,97}{1316} \rceil = \mathbf{9\ pacotes/frame}$

**Análise do Vídeo 2 (`video2.ts`):**
* **FPS:** 23.976 quadros/s
* **Bitrate Médio:** 1.700.000 bps (1700 kb/s)
* **Cálculo (Tamanho):** $\frac{1700000}{8 \times 23.976} = 8863,03\ Bytes/frame$
* **Pacotes por Frame:** $\lceil \frac{8863,03}{1316} \rceil = \mathbf{7\ pacotes/frame}$

**Análise do Vídeo 3 (`video3.ts`):**
* **FPS:** 29.97 quadros/s
* **Bitrate Médio:** 109.000 bps (109 kb/s)
* **Cálculo (Tamanho):** $\frac{109000}{8 \times 29.97} = 454,62\ Bytes/frame$
* **Pacotes por Frame:** $\lceil \frac{454,62}{1316} \rceil = \mathbf{1\ pacote/frame}$

O resultado obtido para o `video3.ts` ilustra um cenário de rede peculiar e altamente eficiente. Enquanto os Vídeos 1 e 2 possuem maior densidade de dados e exigem que cada quadro seja fragmentado na camada de aplicação em 7 a 9 pacotes distintos (para respeitar o limite de 1316 bytes de *payload*), o Vídeo 3 possui uma alta taxa de compressão e baixo *bitrate*. 

Com um tamanho de quadro de apenas $454,62\ Bytes$, um único datagrama da nossa arquitetura é capaz de transportar o frame em sua totalidade. Isso reduz drasticamente a complexidade de processamento no cliente, que não precisa remontar múltiplos pacotes para exibir uma única imagem. Vale ressaltar que, nesse cenário específico, o *payload* do pacote não é totalmente preenchido, resultando em subutilização da capacidade máxima estipulada (restam mais de 800 bytes ociosos por envio), mas garantindo uma latência de montagem de quadro praticamente nula.

---

## 6. Taxa de Transmissão da Rede (Stream a 30fps)

Para determinar a taxa de transmissão real exigida da infraestrutura de rede, é imperativo considerar o *overhead* (peso morto) adicionado pelos cabeçalhos da pilha de protocolos, em contraste com o *bitrate* puro do vídeo. 

Tamanho total do datagrama (frame L2) no cabo:
* Carga útil do Vídeo: 1316 bytes
* Cabeçalhos L7/L4/L3 (RTP + UDP + IPv4): 40 bytes
* Cabeçalho L2 (Ethernet MACs + EtherType): 14 bytes (Desconsiderado no cálculo de IP, mas presente no meio físico)
* **Total transmitido via Socket:** 1356 bytes de Payload de Rede + Ethernet = **1370 bytes por pacote** (ou 10.960 bits).

Para manter um *stream* fluído com a exigência estrita de **30fps** imposta no cenário, a taxa na interface física é dada por:
$$Taxa_{Rede} (bps) = Pacotes\ por\ Frame \times 30\ fps \times 1370\ bytes \times 8\ bits$$

Assumindo o **Vídeo 1** como métrica de cenário, o qual calculamos necessitar de **9 pacotes por frame**:
$$Taxa_{Rede} = 9 \times 30 \times 1370 \times 8$$
$$Taxa_{Rede} = \mathbf{2.959.200\ bps\ (ou\ \approx 2,96\ Mbps)}$$

**Conclusão da Arquitetura:**
Note que o arquivo de vídeo original exige uma leitura média de $2,06\text{ Mbps}$ do disco. No entanto, para transmiti-lo a 30fps pela rede, a placa de rede do contêiner do Servidor precis alocar e transmitir a uma taxa de **$2,96\text{ Mbps}$**. Essa diferença de quase $900\text{ kbps}$ de *overhead* é o "pedágio" de roteamento e transporte exigido pelos cabeçalhos IP/UDP/RTP para garantir a chegada, roteamento e sincronismo dos dados.

## 7. Tratamento do Cabeçalho RTP e Limitações do Ambiente de Simulação

No código desenvolvido para o Cliente, optou-se por uma extração direta do *payload* de vídeo. Após a recepção do datagrama e validação das portas UDP, o cliente isola os dados fatiando o pacote e descartando sumariamente os primeiros 12 bytes correspondentes ao cabeçalho RTP, gravando o restante diretamente no arquivo de saída (`saida.ts`).

**Justificativa Arquitetural:**
Essa abordagem simplificada foi adotada em virtude das características do ambiente de simulação. Como a comunicação entre o Cliente e o Servidor ocorre integralmente dentro de uma rede virtualizada local provida pelo Docker, o canal de transmissão é, na prática, ideal. Não há interferência de roteamento externo complexo, o que garante:
1.  **Ordem Estrita:** Os pacotes chegam exatamente na mesma sequência em que foram enviados.
2.  **Ausência de Perdas e Atrasos:** A latência é mínima e a taxa de descarte de pacotes pelo canal físico é nula.

**Contraste com Redes Reais (WAN):**
Em um cenário de rede real e não-confiável (como a internet pública), o protocolo UDP não garante entrega nem ordenamento. O simples descarte do cabeçalho RTP resultaria em um arquivo de vídeo severamente corrompido, com falhas de decodificação e dessincronização de áudio e vídeo (*lip-sync*). 

No mundo real, os 12 bytes do RTP não seriam descartados, mas lidos pelo cliente para alimentar um **Jitter Buffer**. O *Sequence Number* seria utilizado para reordenar pacotes atrasados e detectar perdas, enquanto o *Timestamp* ditaria o ritmo exato de exibição dos quadros pelo reprodutor de mídia. Portanto, o descarte direto implementado neste laboratório é uma otimização funcional estritamente limitada ao ambiente contido e perfeito do Docker.

## 8. Declaração e Detalhamento do Uso de Inteligência Artificial

Conforme as diretrizes estipuladas no roteiro da disciplina, declaro que o desenvolvimento deste trabalho contou com o suporte de Inteligência Artificial Generativa (modelo Gemini) atuando como ferramenta de assistência à programação e revisão técnica. O uso foi estritamente focado na compreensão arquitetural e da revisão dos conceitos básicos de Redes de Computadores, validação matemática do CheckSum e dos cálculos nas questões anteriores, além boas práticas de engenharia de software, detalhado nas seguintes áreas:

* **Engenharia de Software e Refatoração de Código:** A IA foi utilizada como ferramenta de *Code Review* para modularizar os *scripts* em Python (Cliente e Servidor). Estruturas monolíticas foram refatoradas em funções específicas de empacotamento e desempacotamento (`build_ip_header`, `build_udp_header`, `unpack_rtp`), aplicando o princípio de responsabilidade única para tornar o código mais profissional e legível.
* **Compreensão de Manipulação de Baixo Nível:** Suporte no entendimento avançado da biblioteca `struct` do Python para a formatação correta dos pacotes em *Network Byte Order* (Big-Endian, sintaxe `!BBHHHBBH4s4s`), bem como auxílio na revisão da lógica de operações bit a bit (bitwise) necessárias para o cálculo do *Internet Checksum* (RFC 1071).
* **Validação Matemática (Dimensionamento da Rede):** Auxílio na estruturação das fórmulas e revisão das contas de redes (Questões 5 e 6). A ferramenta ajudou a cruzar os dados extraídos dos metadados dos vídeos reais (taxa de quadros e *bitrate* via VLC) com o *overhead* fixo da pilha de protocolos (40 bytes de L3/L4/L7 + 14 bytes de L2), garantindo a precisão dos cálculos de pacotes por frame e taxa física exigida em bits por segundo.
* **Redação Técnica e Estruturação de Argumentos:** Assistência na formatação do relatório em Markdown e na explicação para o aluno sobre a implementação dos conceitos, e em especial, a fundamentação teórica sobre o contraste entre o funcionamento da arquitetura no ambiente idealizado do Docker versus o mundo real (necessidade do *Jitter Buffer*).