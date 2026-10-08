import { useEffect, useRef, useState } from 'react'

import type { StudyCard } from './study'

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

const SWIPE_THRESHOLD = 80

const controlClass =
  'min-h-[44px] rounded-md border border-border-strong bg-elevated px-4 py-2 text-[13px] font-medium text-text transition-colors hover:border-accent hover:text-accent-soft disabled:opacity-40'

export function FlashcardDeck({ cards }: { cards: StudyCard[] }) {
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)
  const [dragX, setDragX] = useState(0)
  const [dragging, setDragging] = useState(false)
  const reducedMotion = useReducedMotion()
  const gesture = useRef({ startX: 0, moved: false, active: false })

  const total = cards.length
  const card = cards[Math.min(index, total - 1)]

  function goTo(next: number) {
    const clamped = Math.max(0, Math.min(next, total - 1))
    setIndex(clamped)
    setFlipped(false)
    setDragX(0)
  }

  function next() {
    if (index >= total - 1) {
      setDone(true)
    } else {
      goTo(index + 1)
    }
  }

  function previous() {
    goTo(index - 1)
  }

  function flip() {
    setFlipped((value) => !value)
  }

  function reviewAgain() {
    setDone(false)
    goTo(0)
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    gesture.current = { startX: event.clientX, moved: false, active: true }
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!gesture.current.active) return
    const dx = event.clientX - gesture.current.startX
    if (Math.abs(dx) > 8) gesture.current.moved = true
    setDragX(dx)
    if (!dragging) setDragging(true)
  }

  function endGesture() {
    if (!gesture.current.active) return
    const dx = dragX
    gesture.current = { startX: 0, moved: false, active: false }
    setDragging(false)
    setDragX(0)
    if (dx <= -SWIPE_THRESHOLD) next()
    else if (dx >= SWIPE_THRESHOLD) previous()
  }

  function onCardClick() {
    if (!gesture.current.moved) flip()
    gesture.current.moved = false
  }

  function onCardKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      flip()
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      next()
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      previous()
    }
  }

  if (done) {
    return (
      <div className="mx-auto w-full max-w-[700px] text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
          Complete
        </p>
        <p className="mt-2 font-display text-[22px] text-text">
          You&rsquo;ve reviewed all {total} card{total === 1 ? '' : 's'}.
        </p>
        <button type="button" onClick={reviewAgain} className={`${controlClass} mt-4`}>
          Review again
        </button>
      </div>
    )
  }

  const behind = dragX < 0 ? cards[index + 1] : cards[index - 1]
  const behindOpacity = dragging ? Math.min(0.6, Math.abs(dragX) / 220) : 0
  const animate = !reducedMotion && !dragging
  const faceTransition = reducedMotion ? 'none' : 'transform 600ms cubic-bezier(0.3, 0.7, 0.3, 1)'

  return (
    <div className="mx-auto w-full max-w-[700px]">
      <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
        Card {index + 1} of {total}
      </p>
      <div
        aria-hidden="true"
        className="mt-2 flex items-center gap-1.5"
      >
        {cards.map((_, dot) => (
          <span
            key={dot}
            className={`size-1.5 rounded-full ${dot === index ? 'bg-accent' : 'bg-border-strong'}`}
          />
        ))}
        <span className="sr-only">
          Card {index + 1} of {total}
        </span>
      </div>

      <div className="relative mt-3" style={{ perspective: '1200px' }}>
        {behind !== undefined && behindOpacity > 0 ? (
          <div
            aria-hidden="true"
            className="absolute inset-0 rounded-card border border-border bg-surface px-6 py-8"
            style={{ opacity: behindOpacity, transform: 'scale(0.97)' }}
          >
            <p className="font-display text-[19px] leading-snug text-text">
              {behind.question}
            </p>
          </div>
        ) : null}
        <div
          role="button"
          tabIndex={0}
          aria-label={`Flashcard ${index + 1} of ${total}, ${flipped ? 'answer' : 'question'} shown. Activate to ${flipped ? 'show the question' : 'reveal the answer'}.`}
          onClick={onCardClick}
          onKeyDown={onCardKeyDown}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endGesture}
          onPointerCancel={endGesture}
          className="relative min-h-[280px] cursor-pointer touch-pan-y rounded-card border border-border bg-surface px-6 py-8 select-none focus:border-accent focus:outline-none"
          style={{
            transformStyle: 'preserve-3d',
            transform: `translateX(${dragX}px) rotate(${dragX * 0.02}deg)`,
            transition: animate ? 'transform 250ms ease-out' : 'none',
          }}
        >
          <div
            className="absolute inset-0 rounded-card px-6 py-8"
            style={{
              backfaceVisibility: 'hidden',
              opacity: reducedMotion && flipped ? 0 : 1,
              transition: faceTransition,
              transform: flipped && !reducedMotion ? 'rotateY(180deg)' : 'none',
            }}
          >
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
              Question
            </p>
            <p className="mt-3 font-display text-[22px] leading-snug text-text">
              {card.question}
            </p>
            <p className="mt-6 text-[13px] text-text-faint">Click to reveal answer</p>
          </div>
          <div
            className="absolute inset-0 rounded-card bg-elevated px-6 py-8"
            aria-hidden={!flipped}
            style={{
              backfaceVisibility: 'hidden',
              opacity: reducedMotion ? (flipped ? 1 : 0) : 1,
              transition: faceTransition,
              transform: flipped && !reducedMotion ? 'none' : 'rotateY(180deg)',
            }}
          >
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint">
              Answer
            </p>
            <p className="mt-3 text-[15px] leading-relaxed whitespace-pre-wrap text-text">
              {card.answer}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={previous}
          disabled={index === 0}
          className={controlClass}
        >
          ← Previous
        </button>
        <span className="font-mono text-[12px] text-text-muted">
          {index + 1} / {total}
        </span>
        <button type="button" onClick={next} className={controlClass}>
          Next →
        </button>
      </div>
      <div className="mt-2 flex justify-center">
        <button
          type="button"
          onClick={flip}
          className="min-h-[44px] px-4 py-2 text-[13px] text-text-muted underline-offset-4 transition-colors hover:text-text hover:underline"
        >
          Flip card
        </button>
      </div>
    </div>
  )
}
