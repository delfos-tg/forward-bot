# Base image
FROM python:3.12-slim

# Diretório de trabalho dentro do container
WORKDIR /app

# Copiar o arquivo requirements.txt para o diretório de trabalho
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o restante dos arquivos da aplicação para o diretório de trabalho
COPY . .

# Comando padrão para executar o script principal (substitua app.py pelo seu script)
CMD ["python", "main.py"]