import sqlite3
import os

DB_NAME = "integra.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Tabela de Clientes (Empresas)
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cnpj TEXT,
            codigo_sistema TEXT,
            conta_banco_padrao TEXT
        )
    ''')

    # Migration: Adicionar coluna banco_parser se não existir
    try:
        c.execute("ALTER TABLE clientes ADD COLUMN banco_parser TEXT DEFAULT 'Bradesco (PDF)'")
    except sqlite3.OperationalError:
        pass # Coluna já existe
    
    # Tabela de Regras (De/Para)
    c.execute('''
        CREATE TABLE IF NOT EXISTS regras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            padrao_historico TEXT NOT NULL,
            conta_contabil TEXT NOT NULL,
            tipo_match TEXT DEFAULT 'exact', -- exact, contains, regex
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # Índice para performance em buscas de regras
    c.execute('CREATE INDEX IF NOT EXISTS idx_regras_cliente ON regras (cliente_id)')

    conn.commit()
    conn.close()

# --- Funções de Cliente ---
def listar_clientes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nome, codigo_sistema, conta_banco_padrao, banco_parser FROM clientes ORDER BY nome")
    data = c.fetchall()
    conn.close()
    return data

def criar_cliente(nome, codigo, conta_banco, parser='Bradesco (PDF)'):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO clientes (nome, codigo_sistema, conta_banco_padrao, banco_parser) VALUES (?, ?, ?, ?)", 
                  (nome, codigo, conta_banco, parser))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao criar cliente: {e}")
        return False
    finally:
        conn.close()

def get_cliente_by_id(cid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM clientes WHERE id = ?", (cid,))
    row = c.fetchone()
    conn.close()
    return row

# --- Funções de Regras ---
def listar_regras(cliente_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT padrao_historico, conta_contabil FROM regras WHERE cliente_id = ?", (cliente_id,))
    # Retorna como dicionário para compatibilidade com lógica existente
    data = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return data

def salvar_regra(cliente_id, padrao, conta, tipo='exact'):
    conn = get_connection()
    c = conn.cursor()
    # Verifica se já existe para evitar duplicata (upsert simples)
    c.execute("SELECT id FROM regras WHERE cliente_id = ? AND padrao_historico = ?", (cliente_id, padrao))
    exists = c.fetchone()
    
    if exists:
        c.execute("UPDATE regras SET conta_contabil = ? WHERE id = ?", (conta, exists[0]))
    else:
        c.execute("INSERT INTO regras (cliente_id, padrao_historico, conta_contabil, tipo_match) VALUES (?, ?, ?, ?)", 
                  (cliente_id, padrao, conta, tipo))
    conn.commit()
    conn.close()
