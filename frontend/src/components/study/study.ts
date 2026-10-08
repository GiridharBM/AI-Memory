/**
 * Normalizers for generated study artifacts.
 *
 * The backend renders flashcards and quiz sets with byte-exact Markdown
 * (`_render` in `flashcard_handler.py` / `quiz_handler.py`), validated
 * server-side (exact counts, non-empty content, unique prompts, correct
 * answers matching an option). These parsers accept exactly that contract
 * and return `null` for anything else, so unknown content falls back to the
 * existing raw rendering instead of being misread. Nothing is fabricated:
 * a missing correct answer fails the whole quiz parse.
 */

export interface StudyCard {
  question: string
  answer: string
}

export interface StudyQuestion {
  question: string
  options: string[]
  /** Always populated on success; the backend guarantees it. */
  correctAnswer: string
  /** Explanation when the generation included one, else null. */
  feedback: string | null
  /** The backend provides no hints, so this is always null. */
  hint: null
}

function linesOf(content: string): string[] {
  return content.split('\n')
}

function isBlank(line: string): boolean {
  return line.trim().length === 0
}

/** Split `## Card N` / `## Question N` bodies; null unless at least one. */
function splitBlocks(lines: string[], prefix: RegExp): string[][] | null {
  const blocks: string[][] = []
  let current: string[] | null = null
  for (const line of lines) {
    if (prefix.test(line.trim())) {
      if (current !== null) blocks.push(current)
      current = []
    } else if (current !== null) {
      current.push(line)
    }
  }
  if (current !== null) blocks.push(current)
  return blocks.length > 0 ? blocks : null
}

function markerValue(line: string, marker: string): string | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith(marker)) return null
  return trimmed.slice(marker.length).trim()
}

/**
 * Parse `# Flashcards / ## Card N / **Front:** / **Back:**` content.
 * All-or-nothing: every block needs a non-empty front and back.
 */
export function parseFlashcards(content: string): StudyCard[] | null {
  const lines = linesOf(content)
  const start = lines.findIndex((line) => /^#\s+flashcards\s*$/i.test(line.trim()))
  if (start === -1) return null
  const blocks = splitBlocks(lines.slice(start + 1), /^##\s+card\s+\d+\s*$/i)
  if (blocks === null) return null
  const cards: StudyCard[] = []
  for (const block of blocks) {
    let question: string[] | null = null
    let answer: string[] | null = null
    for (const line of block) {
      if (isBlank(line)) continue
      const front = markerValue(line, '**Front:**')
      if (front !== null) {
        if (question !== null) return null
        question = [front]
        continue
      }
      const back = markerValue(line, '**Back:**')
      if (back !== null) {
        if (question === null || answer !== null) return null
        answer = [back]
        continue
      }
      if (answer !== null) answer.push(line.trim())
      else if (question !== null) question.push(line.trim())
      else return null
    }
    const q = (question ?? []).join(' ').trim()
    const a = (answer ?? []).join(' ').trim()
    if (!q || !a) return null
    cards.push({ question: q, answer: a })
  }
  return cards.length > 0 ? cards : null
}

const OPTION_PATTERN = /^([A-Z])\.\s+(.*)$/

/**
 * Parse `# Quiz / ## Question N` content with `A. …` options,
 * a required `**Answer:**` matching one option, and an optional
 * `**Explanation:**`. All-or-nothing.
 */
export function parseQuiz(content: string): StudyQuestion[] | null {
  const lines = linesOf(content)
  const start = lines.findIndex((line) => /^#\s+quiz\s*$/i.test(line.trim()))
  if (start === -1) return null
  const blocks = splitBlocks(lines.slice(start + 1), /^##\s+question\s+\d+\s*$/i)
  if (blocks === null) return null
  const questions: StudyQuestion[] = []
  for (const block of blocks) {
    const prompt: string[] = []
    const options: string[] = []
    let correct: string | null = null
    let feedback: string[] | null = null
    let expectedLetter = 'A'
    for (const line of block) {
      if (isBlank(line)) continue
      if (feedback !== null) {
        feedback.push(line.trim())
        continue
      }
      const answer = markerValue(line, '**Answer:**')
      if (answer !== null) {
        if (options.length < 2 || correct !== null) return null
        correct = answer
        continue
      }
      const explanation = markerValue(line, '**Explanation:**')
      if (explanation !== null) {
        if (correct === null) return null
        feedback = [explanation]
        continue
      }
      const option = OPTION_PATTERN.exec(line.trim())
      if (option !== null && correct === null) {
        if (option[1] !== expectedLetter) return null
        expectedLetter = String.fromCharCode(expectedLetter.charCodeAt(0) + 1)
        options.push(option[2].trim())
        continue
      }
      if (options.length === 0 && correct === null) {
        prompt.push(line.trim())
      } else if (options.length > 0 && correct === null) {
        options[options.length - 1] += ` ${line.trim()}`
      } else {
        return null
      }
    }
    const question = prompt.join(' ').trim()
    const correctAnswer = (correct ?? '').trim()
    if (!question || options.length < 2 || !correctAnswer) return null
    if (!options.includes(correctAnswer)) return null
    const feedbackText = (feedback ?? []).join(' ').trim()
    questions.push({
      question,
      options,
      correctAnswer,
      feedback: feedbackText ? feedbackText : null,
      hint: null,
    })
  }
  return questions.length > 0 ? questions : null
}
