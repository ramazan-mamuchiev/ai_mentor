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

const logger = new ConsoleLogger("lexiro-bot", { level: "info" });

const SYSTEM_PROMPT = `You are Lexiro Bot — a documentation assistant for hardware integration developers.
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

const HELP_MESSAGE = `**Lexiro Bot** — AI-ассистент по документации вендоров

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

function createPrompt() {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("Missing OPENAI_API_KEY");
  }

  const modelOptions: OpenAIChatModelOptions = {
    model: process.env.OPENAI_MODEL || "gemini-2.5-flash",
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

  const lexiroUrl = process.env.LEXIRO_MCP_URL;
  const lexiroKey = process.env.LEXIRO_API_KEY;
  if (!lexiroUrl || !lexiroKey) {
    throw new Error("Missing LEXIRO_MCP_URL or LEXIRO_API_KEY");
  }

  prompt.usePlugin("mcpClient", {
    url: lexiroUrl,
    params: {
      headers: {
        Authorization: `Bearer ${lexiroKey}`,
      },
    },
  });

  return prompt;
}

const prompt = createPrompt();

const app = new App({
  logger,
});

function stripMentions(text: string): string {
  return text.replace(/<at>.*?<\/at>\s*/g, "").trim();
}

app.on("message", async ({ send, activity }) => {
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
      const result = await prompt.send("List all available products");
      await send(result.content || "Не удалось получить список продуктов.");
    } catch (error) {
      logger.error("Error listing products", error);
      await send("Ошибка при получении списка продуктов.");
    }
    return;
  }

  await send({ type: "typing" });

  try {
    const result = await prompt.send(text);
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
    "Привет! Я **Lexiro Bot** — ваш AI-ассистент по документации вендоров. " +
      "Задайте вопрос о любом API, и я найду ответ в базе знаний Lexiro.\n\n" +
      "Напишите **help** для подробной справки."
  );
});

const port = parseInt(process.env.PORT || "3978", 10);
app.start(port).then(() => {
  logger.info(`Lexiro Teams Bot started on port ${port}`);
});
