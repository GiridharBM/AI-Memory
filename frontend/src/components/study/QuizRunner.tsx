import { useState } from 'react'

import type { StudyQuestion } from './study'

const controlClass =
  'min-h-[44px] rounded-md border border-border-strong bg-elevated px-4 py-2 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-40'

export function QuizRunner({ questions }: { questions: StudyQuestion[] }) {
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<(string | null)[]>(
    () => questions.map(() => null),
  )
  const [checked, setChecked] = useState<boolean[]>(() => questions.map(() => false))
  const [finished, setFinished] = useState(false)
  const [reviewing, setReviewing] = useState(false)

  const total = questions.length
  const question = questions[Math.min(index, total - 1)]
  const isChecked = checked[index] ?? false
  const picked = selected[index] ?? null
  const isCorrect = isChecked && picked === question.correctAnswer

  function goTo(next: number) {
    setIndex(Math.max(0, Math.min(next, total - 1)))
  }

  function checkAnswer() {
    if (picked === null) return
    setChecked((prev) => prev.map((value, i) => (i === index ? true : value)))
  }

  function finish() {
    setFinished(true)
    setReviewing(false)
  }

  function retake() {
    setSelected(questions.map(() => null))
    setChecked(questions.map(() => false))
    setFinished(false)
    setReviewing(false)
    setIndex(0)
  }

  const correctCount = questions.filter(
    (item, i) => checked[i] && selected[i] === item.correctAnswer,
  ).length
  const percent = Math.round((correctCount / total) * 100)

  if (finished && !reviewing) {
    return (
      <div className="mx-auto w-full max-w-[700px] text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
          Quiz complete
        </p>
        <p className="mt-2 font-display text-[26px] text-text">
          {correctCount} / {total} correct
        </p>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{percent}%</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <button type="button" onClick={() => setReviewing(true)} className={controlClass}>
            Review answers
          </button>
          <button type="button" onClick={retake} className={controlClass}>
            Retake quiz
          </button>
        </div>
      </div>
    )
  }

  if (finished && reviewing) {
    return (
      <div className="mx-auto w-full max-w-[700px]">
        <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
          Review · {correctCount} / {total} correct
        </p>
        <ul className="mt-3 space-y-4">
          {questions.map((item, i) => {
            const wasCorrect = checked[i] && selected[i] === item.correctAnswer
            return (
              <li key={i} className="rounded-md border border-border px-4 py-3">
                <p className="text-[11px] font-medium text-text-muted">
                  Question {i + 1}{' '}
                  <span className={wasCorrect ? 'text-success' : 'text-danger'}>
                    {wasCorrect ? '✓ Correct' : '✗ Incorrect'}
                  </span>
                </p>
                <p className="mt-1 text-[14px] font-medium text-text">{item.question}</p>
                <p className="mt-1 text-[13px] text-text-muted">
                  Your answer: {selected[i] ?? '—'} · Correct: {item.correctAnswer}
                </p>
                {item.feedback ? (
                  <p className="mt-1 text-[13px] text-text-muted">{item.feedback}</p>
                ) : null}
              </li>
            )
          })}
        </ul>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <button type="button" onClick={() => setReviewing(false)} className={controlClass}>
            Back to results
          </button>
          <button type="button" onClick={retake} className={controlClass}>
            Retake quiz
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-[700px]">
      <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
        Question {index + 1} of {total}
      </p>
      <div aria-hidden="true" className="mt-2 flex items-center gap-1.5">
        {questions.map((_, dot) => (
          <span
            key={dot}
            className={`size-1.5 rounded-full ${dot === index ? 'bg-accent' : 'bg-border-strong'}`}
          />
        ))}
        <span className="sr-only">
          Question {index + 1} of {total}
        </span>
      </div>

      <p className="mt-3 font-display text-[20px] leading-snug text-text">
        {question.question}
      </p>

      <div role="radiogroup" aria-label={`Options for question ${index + 1}`} className="mt-4 space-y-2">
        {question.options.map((option) => {
          const isPicked = picked === option
          const isAnswer = option === question.correctAnswer
          let optionClass =
            'border-border bg-surface hover:border-accent/60'
          let marker: string | null = null
          if (isChecked) {
            if (isAnswer) {
              optionClass = 'border-success bg-success-dim/40'
              marker = '✓ Correct answer'
            } else if (isPicked) {
              optionClass = 'border-danger bg-danger/5'
              marker = '✗ Your answer — incorrect'
            }
          } else if (isPicked) {
            optionClass = 'border-accent bg-accent-dim'
          }
          return (
            <label
              key={option}
              className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-md border px-4 py-2.5 text-[14px] transition-colors ${optionClass} ${isChecked ? 'cursor-default' : ''}`}
            >
              <input
                type="radio"
                name={`quiz-question-${index}`}
                value={option}
                checked={isPicked}
                disabled={isChecked}
                onChange={() =>
                  setSelected((prev) => prev.map((value, i) => (i === index ? option : value)))
                }
                className="size-4 shrink-0 accent-accent"
              />
              <span className="min-w-0 flex-1 text-text">
                {option}
                {marker ? (
                  <span className={`ml-2 text-[12px] font-medium ${isAnswer ? 'text-success' : 'text-danger'}`}>
                    {marker}
                  </span>
                ) : null}
              </span>
            </label>
          )
        })}
      </div>

      {isChecked ? (
        <p role="status" className={`mt-3 text-[14px] font-medium ${isCorrect ? 'text-success' : 'text-danger'}`}>
          {isCorrect ? '✓ Correct' : '✗ Incorrect'}
        </p>
      ) : null}
      {isChecked && question.feedback ? (
        <p className="mt-2 text-[13px] leading-relaxed text-text-muted">{question.feedback}</p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => goTo(index - 1)}
          disabled={index === 0}
          className={controlClass}
        >
          ← Previous
        </button>
        {!isChecked ? (
          <button
            type="button"
            onClick={checkAnswer}
            disabled={picked === null}
            className="min-h-[44px] rounded-md bg-accent px-5 py-2 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-soft disabled:opacity-40"
          >
            Check answer
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => (index >= total - 1 ? finish() : goTo(index + 1))}
          className={controlClass}
        >
          {index >= total - 1 ? 'See results' : 'Next →'}
        </button>
      </div>
    </div>
  )
}
