import socket
import struct
import glob
import os

# --- CONFIGURAÇÕES DE REDE ---
INTERFACE = "eth0"
SRC_IP = "10.0.2.2"  # IP do Cliente
DST_IP = "10.0.1.2"  # IP do Servidor
SRC_PORT = 12345     # Porta do Cliente
DST_PORT = 9999      # Porta do Servidor

# --- FUNÇÕES DE ENGENHARIA DE PACOTES ---

def calculate_checksum(data: bytes) -> int:
    msg = data
    if len(msg) % 2 == 1:
        msg += b'\x00'
    checksum_sum = sum((msg[i] << 8) + msg[i + 1] for i in range(0, len(msg), 2))
    while checksum_sum >> 16:
        checksum_sum = (checksum_sum & 0xFFFF) + (checksum_sum >> 16)
    return (~checksum_sum) & 0xFFFF

def build_ip_header(src_ip: str, dest_ip: str, total_length: int) -> bytes:
    """Constrói o cabeçalho IPv4 e calcula seu próprio checksum."""
    version_ihl = (4 << 4) | 5
    tos = 0
    identification = 0x1234
    flags_frag = (2 << 13) | 0
    ttl = 64
    protocol = socket.IPPROTO_UDP
    src_ip_bin = socket.inet_aton(src_ip)
    dest_ip_bin = socket.inet_aton(dest_ip)

    ip_header_wo_checksum = struct.pack('!BBHHHBBH4s4s', version_ihl, tos, total_length, identification, flags_frag, ttl, protocol, 0, src_ip_bin, dest_ip_bin)
    ip_checksum = calculate_checksum(ip_header_wo_checksum)
    return struct.pack('!BBHHHBBH4s4s', version_ihl, tos, total_length, identification, flags_frag, ttl, protocol, ip_checksum, src_ip_bin, dest_ip_bin)

def build_udp_header(src_ip: str, dest_ip: str, src_port: int, dest_port: int, payload: bytes) -> bytes:
    """Constrói o cabeçalho UDP calculando o checksum com o pseudo-header."""
    udp_length = 8 + len(payload)
    src_ip_bin = socket.inet_aton(src_ip)
    dest_ip_bin = socket.inet_aton(dest_ip)
    protocol = socket.IPPROTO_UDP

    udp_header_wo_checksum = struct.pack('!HHHH', src_port, dest_port, udp_length, 0)
    pseudo_header = struct.pack('!4s4sBBH', src_ip_bin, dest_ip_bin, 0, protocol, udp_length)
    
    udp_checksum = calculate_checksum(pseudo_header + udp_header_wo_checksum + payload)
    udp_checksum = 0xFFFF if udp_checksum == 0 else udp_checksum
    return struct.pack('!HHHH', src_port, dest_port, udp_length, udp_checksum)

def build_udp_packet(src_ip, dest_ip, src_port, dest_port, data) -> bytes:
    """Orquestra a montagem do pacote completo."""
    payload = data if isinstance(data, bytes) else data.encode('utf-8')
    udp_header = build_udp_header(src_ip, dest_ip, src_port, dest_port, payload)
    total_length = 20 + 8 + len(payload)
    ip_header = build_ip_header(src_ip, dest_ip, total_length)
    return ip_header + udp_header + payload

# --- FUNÇÕES DE EXTRACAO DE PACOTES ---
def unpack_iph(pkg: bytes):
    """Extrai os 20 bytes do cabeçalho IP."""
    return struct.unpack('!BBHHHBBH4s4s', pkg[0:20])

def unpack_udp(pkg: bytes):
    """Calcula o offset do IP e extrai os 8 bytes do UDP."""
    ihl = (pkg[0] & 0x0F) * 4
    return struct.unpack('!HHHH', pkg[ihl:ihl + 8])

def unpack_data(pkg: bytes):
    """Extrai estritamente o payload (após IP e UDP)."""
    ihl = (pkg[0] & 0x0F) * 4
    return pkg[ihl + 8:]

def unpack_rtp(rtp_bytes: bytes):
    """Extrai o cabeçalho RTP de 12 bytes"""
    # Desempacota os 12 bytes (!BBHII)
    v_p_x_cc, m_pt, seq_num, timestamp, ssrc = struct.unpack('!BBHII', rtp_bytes[:12])
    return seq_num, timestamp, ssrc

# --- LÓGICA DO CLIENTE ---

def iniciar_cliente():
    # Socket para ENVIAR (Camada 3)
    sender = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    sender.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    
    # Socket para ESCUTAR (Camada 2)
    sniffer = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
    sniffer.bind((INTERFACE, 0))
    
    while True:
        print("\n--- TWITCHE: CLIENTE ---")
        escolha = input("Digite 'catalog' ou 'stream <video.ts>' (ou 'q' para sair): ")
        
        if escolha.lower() == 'q': break
        
        # Monta e envia o pacote de requisição
        pacote = build_udp_packet(SRC_IP, DST_IP, SRC_PORT, DST_PORT, escolha)
        sender.sendto(pacote, (DST_IP, 0))
        
        if escolha == 'catalog':
            receber_catalogo(sniffer)
        elif escolha.startswith('stream '):
            nome_video = escolha.split(' ', 1)[1].strip()
            receber_stream(sniffer, nome_video)

def receber_catalogo(sniffer):
    sniffer.settimeout(5.0)
    try:
        while True:
            raw_data, _ = sniffer.recvfrom(65535)
            # Verifica se é IPv4 (EthType 0x0800)
            if struct.unpack('!H', raw_data[12:14])[0] != 0x0800: continue
            
            ip_packet = raw_data[14:] # Pula cabeçalho Ethernet
            iph = unpack_iph(ip_packet)
            if iph[6] != 17: continue # Garante que é UDP
            
            udph = unpack_udp(ip_packet)
            if udph[1] == SRC_PORT: # Garante que veio para a porta do cliente
                payload = unpack_data(ip_packet)
                print(f"\n[SERVIDOR] {payload.decode('utf-8', errors='ignore')}")
                break
    except socket.timeout:
        print("Tempo esgotado.")
    finally:
        sniffer.settimeout(None)

def receber_stream(sniffer, nome_video):
    arquivo_saida = f"saida-{nome_video}"
    
    # Apaga streams antigos para economizar espaço
    for antigo in glob.glob("saida-*.ts"):
        if antigo != arquivo_saida:
            os.remove(antigo)
            print(f"[*] Removido stream antigo: {antigo}")
    
    print(f"Recebendo stream... Salvo em '{arquivo_saida}'. (Ctrl+C para parar)")
    
    # Timeout de 3s significa fim do stream
    sniffer.settimeout(3.0) 
    
    try:
        with open(arquivo_saida, "wb") as f:
            while True:
                try:
                    raw_data, _ = sniffer.recvfrom(65535)
                    
                    if struct.unpack('!H', raw_data[12:14])[0] != 0x0800: continue
                    ip_packet = raw_data[14:]
                    
                    iph = unpack_iph(ip_packet)
                    if iph[6] != 17: continue # Garante UDP
                    
                    udph = unpack_udp(ip_packet)
                    
                    if udph[1] == SRC_PORT:
                        payload_udp = unpack_data(ip_packet)
                        
                        # 1. Isola os 12 bytes do RTP
                        rtp_header = payload_udp[:12]
                        
                        # 2. Desempacota e lê os valores!
                        seq_num, timestamp, ssrc = unpack_rtp(rtp_header)
                        
                        # OPCIONAL: Você pode imprimir a cada 100 pacotes só pra ver a mágica acontecendo
                        if seq_num % 100 == 0:
                            print(f"[*] Recebido Pacote RTP -> Seq: {seq_num} | Timestamp: {timestamp}")
                        
                        # 3. Agora sim, pega do byte 12 em diante (o vídeo real) e salva
                        payload_video = payload_udp[12:] 
                        f.write(payload_video)
                        
                except socket.timeout:
                    print("\n[!] O servidor parou de enviar pacotes. Stream concluído com sucesso!")
                    break 
                    
    except KeyboardInterrupt:
        print("\nStream interrompido manualmente pelo usuário.")
    finally:
        sniffer.settimeout(None)

if __name__ == "__main__":
    iniciar_cliente()