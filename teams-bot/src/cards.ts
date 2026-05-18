/**
 * Adaptive Card builders for formatting AI Mentor bot responses in Teams.
 *
 * Uses raw Adaptive Card JSON schema (v1.5) for maximum compatibility
 * across Teams desktop, web, and mobile clients.
 */

const MAX_BODY_LENGTH = 15000;

export interface AdaptiveCardPayload {
  type: "AdaptiveCard";
  $schema: string;
  version: string;
  body: unknown[];
  actions?: unknown[];
}

export function buildAnswerCard(
  question: string,
  answer: string
): AdaptiveCardPayload {
  const truncated =
    answer.length > MAX_BODY_LENGTH
      ? answer.slice(0, MAX_BODY_LENGTH) + "\n\n_(ответ обрезан из-за ограничений Teams)_"
      : answer;

  const codeBlockSections = splitByCodeBlocks(truncated);

  const bodyElements: unknown[] = [
    {
      type: "TextBlock",
      text: `**Вопрос:** ${escapeMarkdown(question)}`,
      wrap: true,
      weight: "Bolder",
      size: "Medium",
    },
    {
      type: "ColumnSet",
      columns: [
        {
          type: "Column",
          width: "stretch",
          items: [
            {
              type: "TextBlock",
              text: "AI Mentor Documentation Assistant",
              wrap: true,
              isSubtle: true,
              size: "Small",
            },
          ],
        },
      ],
    },
    {
      type: "Container",
      separator: true,
      items: codeBlockSections.map((section) => {
        if (section.isCode) {
          return {
            type: "TextBlock",
            text: `\`\`\`\n${section.content}\n\`\`\``,
            wrap: true,
            fontType: "Monospace",
            size: "Small",
          };
        }
        return {
          type: "TextBlock",
          text: section.content,
          wrap: true,
        };
      }),
    },
  ];

  return {
    type: "AdaptiveCard",
    $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
    version: "1.5",
    body: bodyElements,
  };
}

export function buildErrorCard(errorMessage: string): AdaptiveCardPayload {
  return {
    type: "AdaptiveCard",
    $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
    version: "1.5",
    body: [
      {
        type: "TextBlock",
        text: "⚠️ Ошибка",
        wrap: true,
        weight: "Bolder",
        color: "Attention",
      },
      {
        type: "TextBlock",
        text: errorMessage,
        wrap: true,
      },
    ],
  };
}

interface TextSection {
  content: string;
  isCode: boolean;
}

function splitByCodeBlocks(text: string): TextSection[] {
  const sections: TextSection[] = [];
  const codeBlockRegex = /```[\w]*\n([\s\S]*?)```/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const before = text.slice(lastIndex, match.index).trim();
      if (before) {
        sections.push({ content: before, isCode: false });
      }
    }
    sections.push({ content: match[1].trim(), isCode: true });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    const remaining = text.slice(lastIndex).trim();
    if (remaining) {
      sections.push({ content: remaining, isCode: false });
    }
  }

  if (sections.length === 0) {
    sections.push({ content: text, isCode: false });
  }

  return sections;
}

function escapeMarkdown(text: string): string {
  return text.replace(/([*_~`])/g, "\\$1");
}
