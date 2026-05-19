import "dotenv/config";

import { App } from "@microsoft/teams.apps";
import { MessageActivity } from "@microsoft/teams.api";
import { ChatPrompt } from "@microsoft/teams.ai";
import { McpClientPlugin } from "@microsoft/teams.mcpclient";
import {
  OpenAIChatModel,
  type OpenAIChatModelOptions,
} from "@microsoft/teams.openai";
import { ConsoleLogger } from "@microsoft/teams.common";

import { buildAnswerCard, buildErrorCard } from "./cards.js";

const logger = new ConsoleLogger("ai-mentor-bot", { level: "info" });

const _RETRYABLE_STATUS_CODES = new Set([429, 500, 503]);
const _MAX_RETRIES = 3;
const _RETRY_BASE_DELAY = 2000;

async function withRetry<T>(fn: () => Promise<T>, label: string): Promise<T> {
  let lastErr: any;
  for (let attempt = 0; attempt <= _MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      const delay = _RETRY_BASE_DELAY * 2 ** (attempt - 1);
      logger.warn(`${label}: ${lastErr?.status ?? "?"}, retry ${attempt + 1}/${_MAX_RETRIES + 1} in ${delay}ms`);
      await new Promise((r) => setTimeout(r, delay));
    }
    try {
      return await fn();
    } catch (err: any) {
      lastErr = err;
      const status = err?.status ?? err?.response?.status;
      if (!_RETRYABLE_STATUS_CODES.has(status) || attempt === _MAX_RETRIES) throw err;
    }
  }
  throw lastErr;
}

const SYSTEM_PROMPT = `You are AI Mentor Bot — a documentation assistant for hardware integration developers.
Your knowledge base contains API documentation for IP cameras, access controllers, intercoms,
video management systems (VMS), PSIM platforms, and IoT SDKs.

RULES:
- ALWAYS use the available MCP tools to find information. Never guess or hallucinate API details.
- Call list_products first if you don't know what products are available.
- Call get_api_lifecycle FIRST when writing integration code for any product.
- Use search_documentation for general questions about APIs.
- Use get_api_endpoint when the user asks about a specific endpoint path.
- Use get_code_examples when the user asks for code snippets.
- Use grep_docs for exact string matches (error codes, IP addresses, config keys).
- Always cite the source: product name, document title, and section.
- Answer in the same language as the question (Russian if asked in Russian, English if in English).
- Keep answers concise but complete. Include code examples when relevant.
- If documentation quality is low or results are uncertain, warn the user.`;

const HELP_MESSAGE = `**AI Mentor Bot** — AI-ассистент по документации вендоров

**Как использовать:**
Просто напишите вопрос, например:
- _Как открыть дверь через HikCentral HTTP API?_
- _Покажи RTSP URL для камеры Hikvision DS-2CD2347G2-LU_
- _Какой формат аутентификации у Axxon One gRPC API?_
- _Код на C# для подключения к контроллеру Trezor_

**Команды:**
- **products** — показать список доступных продуктов
- **help** — показать эту справку

Все вопросы и ответы видны участникам чата. В каналах ответы приходят в тред.`;

const _FALLBACK_MODEL = "gemini-2.5-flash";

function createPrompt(modelOverride?: string) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("Missing OPENAI_API_KEY");
  }

  const model = modelOverride || process.env.OPENAI_MODEL || "gemini-2.5-flash";
  const modelOptions: OpenAIChatModelOptions = {
    model,
    apiKey,
    baseUrl: process.env.OPENAI_BASE_URL,
    logger,
  };

  const mcpPlugin = new McpClientPlugin({ logger });
  const prompt = new ChatPrompt(
    {
      instructions: SYSTEM_PROMPT,
      model: new OpenAIChatModel(modelOptions),
    },
    [mcpPlugin]
  );

  const aiMentorUrl = process.env.AI_MENTOR_MCP_URL;
  const aiMentorKey = process.env.AI_MENTOR_API_KEY;
  if (!aiMentorUrl || !aiMentorKey) {
    throw new Error("Missing AI_MENTOR_MCP_URL or AI_MENTOR_API_KEY");
  }

  prompt.usePlugin("mcpClient", {
    url: aiMentorUrl,
    params: {
      headers: {
        Authorization: `Bearer ${aiMentorKey}`,
      },
    },
  });

  return prompt;
}

const primaryModel = process.env.OPENAI_MODEL || "gemini-2.5-flash";
const prompt = createPrompt();
const fallbackPrompt = primaryModel !== _FALLBACK_MODEL ? createPrompt(_FALLBACK_MODEL) : null;

async function sendWithFallback(text: string, label: string) {
  try {
    return await withRetry(() => prompt.send(text), label);
  } catch (err: any) {
    if (!fallbackPrompt) throw err;
    const status = err?.status ?? err?.response?.status;
    if (!_RETRYABLE_STATUS_CODES.has(status)) throw err;
    logger.warn(`${label}: primary model exhausted retries, falling back to ${_FALLBACK_MODEL}`);
    return await withRetry(() => fallbackPrompt.send(text), `${label}_fallback`);
  }
}

const app = new App({
  logger,
});

function stripMentions(text: string): string {
  return text.replace(/<at>.*?<\/at>\s*/g, "").trim();
}

const ALLOWED_TENANT_ID = process.env.ALLOWED_TENANT_ID;
const ALLOWED_DOMAIN = process.env.ALLOWED_DOMAIN || "axxonsoft.dev";

function isAuthorized(activity: { from: any; channelData?: any }): { ok: boolean; reason?: string } {
  const tenantId = activity.channelData?.tenant?.id;
  if (ALLOWED_TENANT_ID && tenantId && tenantId !== ALLOWED_TENANT_ID) {
    return { ok: false, reason: `wrong tenant ${tenantId}` };
  }

  const upn: string | undefined = activity.from?.userPrincipalName;
  if (upn && !upn.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`)) {
    return { ok: false, reason: `unauthorized domain in UPN ${upn}` };
  }

  return { ok: true };
}

app.on("message", async ({ send, activity }) => {
  const auth = isAuthorized(activity as any);
  if (!auth.ok) {
    logger.warn(`Access denied: ${auth.reason}`);
    await send(`Доступ ограничен для пользователей @${ALLOWED_DOMAIN}`);
    return;
  }

  const rawText = activity.text?.trim();
  if (!rawText) return;

  const text = stripMentions(rawText);
  if (!text) return;

  const lowerText = text.toLowerCase();

  if (lowerText === "help" || lowerText === "/help" || lowerText === "помощь") {
    await send(HELP_MESSAGE);
    return;
  }

  if (
    lowerText === "products" ||
    lowerText === "/products" ||
    lowerText === "продукты"
  ) {
    await send({ type: "typing" });
    try {
      const result = await sendWithFallback("List all available products", "list_products");
      await send(result.content || "Не удалось получить список продуктов.");
    } catch (error) {
      logger.error("Error listing products", error);
      await send("Ошибка при получении списка продуктов.");
    }
    return;
  }

  await send({ type: "typing" });

  try {
    const result = await sendWithFallback(text, "chat");
    const content =
      result.content ||
      "Не удалось найти ответ. Попробуйте переформулировать вопрос.";

    if (content.length > 2000) {
      const card = buildAnswerCard(text, content);
      await send(
        new MessageActivity("").addAttachments({
          contentType: "application/vnd.microsoft.card.adaptive",
          content: card,
        })
      );
    } else {
      await send(content);
    }
  } catch (error) {
    logger.error("Error processing message", error);
    const errorCard = buildErrorCard(
      "Произошла ошибка при обработке запроса. Попробуйте позже или переформулируйте вопрос."
    );
    await send(
      new MessageActivity("").addAttachments({
        contentType: "application/vnd.microsoft.card.adaptive",
        content: errorCard,
      })
    );
  }
});

app.on("install.add", async ({ send }) => {
  await send(
    "Привет! Я **AI Mentor Bot** — ваш AI-ассистент по документации вендоров. " +
      "Задайте вопрос о любом API, и я найду ответ в базе знаний AI Mentor.\n\n" +
      "Напишите **help** для подробной справки."
  );
});

const port = parseInt(process.env.PORT || "3978", 10);
app.start(port).then(() => {
  logger.info(`AI Mentor Teams Bot started on port ${port}`);
});
