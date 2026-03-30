import socket
import struct
import time
import os

# --- CONFIGURAÇÕES DE REDE ---
INTERFACE = "eth0"
SRC_IP = "10.0.1.2"
SRC_PORT = 9999

# --- FUNÇÕES AUXILIARES PARA DESMONTAR PACOTES ---
def unpack_iph(pkg: bytes):
    """Extrai os 20 bytes do cabeçalho IP e retorna uma tupla."""
    # Lembre-se: pkg já deve vir sem os 14 bytes do Ethernet!
    return struct.unpack('!BBHHHBBH4s4s', pkg[0:20])

def unpack_udp(pkg: bytes):
    """Calcula onde o IP termina e extrai os 8 bytes do UDP."""
    ihl = (pkg[0] & 0x0F) * 4
    return struct.unpack('!HHHH', pkg[ihl:ihl + 8])

def unpack_data(pkg: bytes):
    """Calcula onde o IP e o UDP terminam e retorna apenas o payload."""
    ihl = (pkg[0] & 0x0F) * 4
    return pkg[ihl + 8:]

# --- FUNÇÕES PARA MONTAR PACOTES ---
def calculate_checksum(data: bytes) -> int:
    msg = data
    if len(msg) % 2 == 1:
        msg += b'\x00'
    checksum_sum = sum((msg[i] << 8) + msg[i + 1] for i in range(0, len(msg), 2))
    while checksum_sum >> 16:
        checksum_sum = (checksum_sum & 0xFFFF) + (checksum_sum >> 16)
    return (~checksum_sum) & 0xFFFF

def build_ip_header(src_ip: str, dest_ip: str, total_length: int) -> bytes:
    """Constrói o cabeçalho IPv4 (20 bytes) e calcula seu checksum."""
    version_ihl = (4 << 4) | 5
    tos = 0
    identification = 0x1234
    flags_frag = (2 << 13) | 0
    ttl = 64
    protocol = socket.IPPROTO_UDP
    src_ip_bin = socket.inet_aton(src_ip)
    dest_ip_bin = socket.inet_aton(dest_ip)

    # Monta sem checksum para calcular
    ip_header_wo_checksum = struct.pack(
        '!BBHHHBBH4s4s', 
        version_ihl, tos, total_length, identification, flags_frag, ttl, protocol, 0, src_ip_bin, dest_ip_bin
    )
    
    ip_checksum = calculate_checksum(ip_header_wo_checksum)
    
    # Monta a versão final com o checksum calculado
    ip_header = struct.pack(
        '!BBHHHBBH4s4s', 
        version_ihl, tos, total_length, identification, flags_frag, ttl, protocol, ip_checksum, src_ip_bin, dest_ip_bin
    )
    
    return ip_header

def build_udp_header(src_ip: str, dest_ip: str, src_port: int, dest_port: int, payload: bytes) -> bytes:
    """Constrói o cabeçalho UDP (8 bytes) calculando o checksum com o pseudo-header IP."""
    udp_length = 8 + len(payload)
    src_ip_bin = socket.inet_aton(src_ip)
    dest_ip_bin = socket.inet_aton(dest_ip)
    protocol = socket.IPPROTO_UDP

    # Monta o header UDP sem checksum
    udp_header_wo_checksum = struct.pack('!HHHH', src_port, dest_port, udp_length, 0)
    
    # Monta o Pseudo-Header exigido pela RFC 768 para calcular o checksum do UDP
    pseudo_header = struct.pack('!4s4sBBH', src_ip_bin, dest_ip_bin, 0, protocol, udp_length)
    
    # A grande soma: Pseudo-Header + Header UDP Zerado + Dados
    udp_checksum = calculate_checksum(pseudo_header + udp_header_wo_checksum + payload)
    udp_checksum = 0xFFFF if udp_checksum == 0 else udp_checksum
    
    # Retorna os 8 bytes finais
    udp_header = struct.pack('!HHHH', src_port, dest_port, udp_length, udp_checksum)
    
    return udp_header

def build_udp_packet(src_ip: str, dest_ip: str, src_port: int, dest_port: int, data) -> bytes:
    """Orquestra a montagem do pacote completo: IP + UDP + Payload."""
    # Garante que os dados estão em formato de bytes
    payload = data if isinstance(data, bytes) else data.encode('utf-8')
    
    # 1. Constrói o UDP
    udp_header = build_udp_header(src_ip, dest_ip, src_port, dest_port, payload)
    
    # 2. Constrói o IP (Lembrando que o tamanho total = 20 (IP) + 8 (UDP) + Payload)
    total_length = 20 + 8 + len(payload)
    ip_header = build_ip_header(src_ip, dest_ip, total_length)
    
    # 3. Encapsula tudo (Boneca Russa)
    pacote_completo = ip_header + udp_header + payload
    
    return pacote_completo

def build_rtp_header(seq_num, timestamp, ssrc):
    version, padding, extension, csrc_count, marker = 2, 0, 0, 0, 0
    payload_type = 33 # MP2T
    byte1 = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
    byte2 = (marker << 7) | payload_type
    return struct.pack('!BBHII', byte1, byte2, seq_num, timestamp, ssrc)

# --- FUNÇÃO PRINCIPAL PARA PROCESSAR COMANDOS ---
def processar_comandos():
    sender = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    sender.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    
    sniffer = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
    sniffer.bind((INTERFACE, 0))
    
    print(f"Servidor aguardando em {SRC_IP}:{SRC_PORT}...")

    while True:
        raw_data, _ = sniffer.recvfrom(65535)
        
        # Filtro básico de tamanho e protocolo Ethernet (apenas IPv4)
        if len(raw_data) < 42: continue
        if struct.unpack('!H', raw_data[12:14])[0] != 0x0800: continue
        
        # Pula a Camada 2 (Ethernet)
        ip_packet = raw_data[14:]
        
        # --- 1. PROCESSA O CABEÇALHO IP ---
        iph = unpack_iph(ip_packet)
        protocolo_ip = iph[6]
        
        if protocolo_ip != 17: continue # Se não for UDP (17), ignora
        
        # --- 2. PROCESSA O CABEÇALHO UDP ---
        udph = unpack_udp(ip_packet)
        src_port_client = udph[0]
        dst_port_serv = udph[1]

        # --- 3. VALIDAÇÃO E EXTRAÇÃO DOS DADOS ---
        if dst_port_serv == SRC_PORT:
            # O IP de origem está no índice 8 da tupla do unpack_iph
            src_ip_client = socket.inet_ntoa(iph[8]) 
            
            # Pega o payload (a mensagem) usando a nossa nova função
            payload = unpack_data(ip_packet)
            mensagem = payload.decode('utf-8', errors='ignore').strip()
            
            print(f"[REDE] Pedido de {src_ip_client}: '{mensagem}'")
            
            # --- 4. ROTEAMENTO DO COMANDO ---
            if mensagem == "catalog":
                caminho_videos = "./videos"
                videos = os.listdir(caminho_videos) if os.path.exists(caminho_videos) else []
                resposta = "Catálogo: " + ", ".join(videos)
                pacote = build_udp_packet(SRC_IP, src_ip_client, SRC_PORT, src_port_client, resposta)
                sender.sendto(pacote, (src_ip_client, 0))
                
            elif mensagem.startswith("stream"):
                video_nome = mensagem.split(" ")[1] if " " in mensagem else ""
                iniciar_stream(sender, video_nome, src_ip_client, src_port_client)

def iniciar_stream(sender, nome_arquivo, target_ip, target_port):
    caminho = f"./videos/{nome_arquivo}"
    if not os.path.exists(caminho):
        print(f"Erro: Arquivo {caminho} não encontrado.")
        return

    print(f"Iniciando stream de {nome_arquivo} para {target_ip}:{target_port}...")
    seq, ts, ssrc = 0, 0, 12345
    
    with open(caminho, "rb") as f:
        while True:
            chunk = f.read(1316)
            if not chunk: break
            
            rtp_header = build_rtp_header(seq, ts, ssrc)
            pacote = build_udp_packet(SRC_IP, target_ip, SRC_PORT, target_port, rtp_header + chunk)
            sender.sendto(pacote, (target_ip, 0))
            
            seq = (seq + 1) % 65536
            ts += 3600
            time.sleep(0.005)
    print("Stream finalizado.")

if __name__ == "__main__":
    processar_comandos()