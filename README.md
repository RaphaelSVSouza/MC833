# Twitche: Streaming de Vídeo com Raw Sockets

**Disciplina:** MC833 - Redes de Computadores (Unicamp)  
**Autor:** Raphael Salles Vitor de Souza | RA: 223641

## 📌 Sobre o Projeto
Este repositório contém a implementação do projeto "Twitche", focado no desenvolvimento de um sistema de streaming de vídeo do zero. O objetivo principal é a compreensão prática da pilha de protocolos da internet através da construção e desempacotamento manual de cabeçalhos **IPv4, UDP e RTP** utilizando *Raw Sockets* em Python.

A aplicação conta com um Servidor que hospeda um catálogo de vídeos (`.ts`) e um Cliente capaz de solicitar e receber fluxos de mídia em tempo real.

## 🐳 Ambiente de Desenvolvimento (Docker)
Este projeto é executado sobre um ambiente **Docker** base, integralmente fornecido pelo professor da disciplina. 

Esse ambiente em contêineres foi projetado para simular uma topologia de rede controlada (composta por nós de Cliente, Roteador e Servidor). Ele servirá como a infraestrutura fundamental e padronizada sobre a qual desenvolveremos, testaremos e expandiremos as implementações de rede ao longo de todo o semestre.

## ⚙️ Estrutura do Repositório
* `cliente.py`: Lógica do cliente (solicitação de catálogo, recepção do stream e extração do *payload* de vídeo).
* `servidor.py`: Lógica do servidor (escuta na porta 9999, encapsulamento RTP/UDP/IP e envio dos *chunks* de vídeo).
* `videos/`: Diretório contendo os arquivos de vídeo MPEG-TS (`.ts`) utilizados para o streaming.
* `relatorios/`: Relatórios respondendo as questões elaboradas pelo professor da disciplina, escritos em markdown

## 🚀 Como Executar

Ambiente base (docker e scripts *".sh"*) fornecidos pelo professor. Para entender o processo de execução, acessar `Ambiente-Professor.md` na raiz do repositório.