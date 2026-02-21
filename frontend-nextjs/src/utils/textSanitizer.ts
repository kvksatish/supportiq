/**
 */
export function sanitizePlainText(markdown: string): string {
  if (!markdown) return '';

  return markdown
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/(?<!\w)\*(?!\*)(.*?)\*(?!\*)/g, '$1')
    .replace(/(?<!\w)_(?!_)(.*?)_(?!_)/g, '$1')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*]\s+/gm, '• ')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/^>\s+/gm, '')
    .replace(/\s{3,}/g, '  ')
    .trim();
}

/**
 */
export function hasMarkdownFormatting(text: string): boolean {
  if (!text) return false;
  const markdownPatterns = [
    /\*\*.*\*\*/,  // Bold
    /`.*`/,        // Code
    /\[.*\]\(.*\)/ // Links
  ];
  return markdownPatterns.some(pattern => pattern.test(text));
}
