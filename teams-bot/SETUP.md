# AI Mentor Teams Bot

AI-бот для Microsoft Teams, который ищет по документации вендоров через AI Mentor MCP.

## Архитектура

```
Teams Chat/Channel
    |
    v
Azure Bot Service
    |
    v
Teams SDK Bot (Node.js)  -->  MCP Client  -->  AI Mentor MCP Server (ai-mentor.ru/mcp)
    |                                               |
    v                                               v
OpenAI / Azure OpenAI                    PostgreSQL + pgvector
(LLM с function calling)                (документация вендоров)
```

## Предварительные требования

- Node.js 20+
- Azure-подписка (для Bot Service)
- API-ключ AI Mentor (`ipx_...`) — получить на ai-mentor.ru -> Settings -> API Keys
- API-ключ OpenAI (`sk-...`) или Azure OpenAI

## 1. Регистрация Azure Bot Service

1. Откройте [Azure Portal](https://portal.azure.com)
2. Найдите **Azure Bot** -> нажмите **Create**
3. Заполните форму:
   - **Bot handle**: `ai-mentor-teams-bot`
   - **Pricing tier**: F0 (Free) для тестирования
   - **Type of App**: Multi Tenant
   - **Microsoft App ID**: Create new -> Auto create
4. После создания перейдите в ресурс:
   - **Configuration** -> скопируйте **Microsoft App ID** -> это ваш `BOT_ID`
   - **Manage Password** -> **New client secret** -> скопируйте значение -> это `BOT_PASSWORD`
5. **Channels** -> добавьте **Microsoft Teams**
6. **Configuration** -> **Messaging endpoint**: `https://your-domain.com/api/messages`

## 2. Настройка проекта

```bash
cd teams-bot
cp .env.example .env
npm install
```

### Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_ID` | Да | Microsoft App ID из Azure Bot |
| `BOT_PASSWORD` | Да | Client secret из Azure Bot |
| `OPENAI_API_KEY` | Да* | API-ключ OpenAI |
| `AZURE_OPENAI_API_KEY` | Да* | API-ключ Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | Нет | Endpoint Azure OpenAI |
| `AZURE_OPENAI_DEPLOYMENT` | Нет | Имя деплоя (по умолчанию gpt-4o) |
| `AI_MENTOR_MCP_URL` | Да | URL MCP-сервера AI Mentor |
| `AI_MENTOR_API_KEY` | Да | API-ключ AI Mentor (ipx_...) |
| `PORT` | Нет | Порт сервера (по умолчанию 3978) |

*Нужен либо `OPENAI_API_KEY`, либо `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`

## 3. Локальный запуск

```bash
npm run dev
```

Для тестирования с Teams используйте ngrok:

```bash
ngrok http 3978
# Скопируйте HTTPS URL -> Azure Bot -> Configuration -> Messaging endpoint
```

## 4. Деплой

### Вариант A: Azure App Service

```bash
npm run build
az webapp up --name ai-mentor-teams-bot --runtime "NODE:20-lts"
az webapp config appsettings set --name ai-mentor-teams-bot \
  --settings BOT_ID=... BOT_PASSWORD=... OPENAI_API_KEY=... \
  AI_MENTOR_MCP_URL=https://ai-mentor.ru/mcp AI_MENTOR_API_KEY=ipx_...
```

### Вариант B: Docker

```bash
docker build -t ai-mentor-teams-bot .
docker compose up -d
```

## 5. Установка бота в Teams

### Для разработки (sideloading)

1. Создайте ZIP-архив из папки `appPackage/` (manifest.json + иконки)
2. Teams -> Apps -> **Manage your apps** -> **Upload a custom app**
3. Добавьте бота в чат или канал

### Для организации (Teams Admin Center)

1. Откройте [Teams Admin Center](https://admin.teams.microsoft.com)
2. **Teams apps** -> **Manage apps** -> **Upload new app**
3. Настройте app setup policy для нужных пользователей

## 6. Использование

В чате или канале: `@AI Mentor Bot как открыть дверь через HikCentral API?`

### Команды
- `help` — справка
- `products` — список доступных продуктов

### Функции
- Ответы в тредах (в каналах)
- Adaptive Cards для длинных ответов
- 11 инструментов AI Mentor: поиск, endpoint lookup, code examples, lifecycle
- Русский и английский языки

## Стоимость

| Компонент | Стоимость/мес |
|---|---|
| Azure Bot Service F0 | Бесплатно |
| Azure App Service B1 | ~$13 |
| OpenAI API (gpt-4o) | ~$5-20 |
| AI Mentor API | Включено |
| **Итого** | **~$20-35/мес** |
