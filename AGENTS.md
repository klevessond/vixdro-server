# Servidor do vixdro (Django + Django REST Framework)

API do app vixdro/Orçaminio. Cada vidraceiro é um usuário (`contas.Vidraceiro`) e só enxerga os próprios dados.

## Comandos

```bash
pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run   # não pode haver migração faltando
# Testes (rodam num SQLite, sem precisar do PostgreSQL):
SECRET_KEY=teste DB_ENGINE=django.db.backends.sqlite3 DB_NAME=/tmp/teste.sqlite3 MEDIA_ROOT=/tmp/media-teste python manage.py test testes
```

Rode os três antes de cada commit. `git status` limpo: nada alterado fica fora do commit.

## Regras de segurança

### Cada vidraceiro só vê o que é dele
- Todo `get_queryset` começa filtrando por `vidraceiro=self.request.user` (ou pelo caminho até ele, ex: `projeto__vidraceiro`).
- O dono é sempre `request.user`, definido no `perform_create`. Nunca um campo enviado pelo app.
- Campo que aponta para outro registro (cliente, projeto, conta, condição, peça pronta) usa `PrimaryKeyRelatedField` com `queryset` filtrado pelo usuário no `__init__` do serializer. Itens do catálogo passam por `item_visivel()`.
- Id criado no app (UUID): se já existe e é de outro dono, recusa; se é do mesmo dono, responde 200 sem duplicar.
- Rota nova = teste novo em `testes/test_isolamento.py` mostrando que outro vidraceiro recebe 404 ou 400.

### Login e senha
- Senha nova passa por `validate_password` (a política fica em `AUTH_PASSWORD_VALIDATORS`).
- Rota pública (`AllowAny`) sempre tem limite de tentativas (`throttle_classes`).
- `NUM_PROXIES` precisa bater com a quantidade de proxies na frente do Django.

### Recurso do Pro
- `permission_classes = [IsAuthenticated, RequerPro]`. Esconder o botão no app não protege nada.

### Imagens
- Toda imagem enviada é aberta por `projetos.fotos.abrir_imagem` (confere formato e tamanho) e regravada pelo servidor. Nunca gravar no disco o arquivo como veio, nem usar nome de arquivo enviado pelo app.

### Entradas e erros
- Dado do app é validado em serializer. Em `request.data.get(...)` direto, converter e validar antes de usar.
- Nada de SQL montado com texto. Só o ORM (ou parâmetros `%s`).
- Gravação em mais de uma tabela vai em `transaction.atomic`.
- Ação que não pode acontecer duas vezes (pedido ao fornecedor, numeração) trava a linha com `select_for_update` e confere de novo dentro da transação.
- Mensagem de erro para o app em português, sem trecho de exceção interna.

### Segredos e arquivos
- Segredo só no `.env` (modelo em `env.exemplo`). Chave de fornecedor nunca no banco.
- `media/`, `*.sqlite3` e `.env` não entram no git.
- Produção: `DEBUG=False`, HTTPS, `ALLOWED_HOSTS` e `CORS_ALLOWED_ORIGINS` só com os domínios reais.

### Fornecedores
- O resto do sistema fala com o fornecedor só pelo adaptador (`fornecedores/adaptadores`).
- Toda chamada externa tem `timeout`. O envio de pedido é idempotente pelo `id_vixdro`.
