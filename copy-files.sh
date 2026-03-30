#!/bin/bash

# Copia arquivos do host para os containers
docker cp ./cliente/. client:/app
docker cp ./servidor/. servidor:/app
docker cp ./roteador/. roteador:/app

# Copia o último arquivo de saída (mais recente) do container para o host
ultimo=$(docker exec client ls -t /app/ 2>/dev/null | grep '^saida' | head -1)
if [ -n "$ultimo" ]; then
    # Remove arquivos saida antigos do host antes de copiar o novo
    rm -f ./cliente/saida-*.ts 2>/dev/null
    docker cp "client:/app/$ultimo" "./cliente/$ultimo" && echo "$ultimo copiado para ./cliente/"
else
    echo "Nenhum arquivo saida* encontrado no container."
fi
