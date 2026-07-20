![](https://www.youtube.com/watch?v=-MPGU2a67Ls)

Watch GPT-5.6 build a playable, celestial-themed card game in Codex from a short, open-ended prompt.  
  
In this demo, GPT-5.6 designs the core mechanics, generates custom artwork, adds levels and a soundtrack, tests the gameplay, and keeps improving the build. Along the way, see how programmatic tool calling, Max Reasoning, and subagents help it take on longer-running work - using a sandbox to process tool results, split work in parallel, and bring everything back into one polished game.  
  
Check out the game here: https://asterism.openai.chatgpt.site/  
  
Chapters  
00:00 Introducing GPT-5.6  
00:17 Building a game in Codex  
00:52 Programmatic tool calling  
01:07 Reasoning and subagents  
01:35 GPT-5.6 in the API

## Transcript

### Introducing GPT-5.6

**0:02** · Today, we're making the GPT-5.6 series of models generally available.

**0:07** · Across the family, GPT-5.6 delivers more intelligence per token and is better at staying on track, even with ambiguous prompts.

**0:15** · Let's take a look at what it can do.

### Building a game in Codex

**0:17** · I used GPT-5.6 in Codex to build a brand new card game from a short, intentionally open-ended prompt, something I'd actually want to play.

**0:27** · The model designed the core game mechanics, generated the artwork, and shipped a working first version.

**0:33** · But I had an idea for an even better version, so I asked it to keep going, add levels, enhance the game mechanics, customize the artwork, and create a soundtrack.

**0:43** · I love how thorough the model is.

**0:45** · I didn't have to worry about designing every screen, defining every interaction, or managing a stack of tickets.

### Programmatic tool calling

**0:52** · What I found really cool with GPT-5.6 is programmatic tool calling.

**0:56** · When building the game, the model was able to call tools from a sandbox and avoid a lot of back and forth between the tool output and the context window.

**1:04** · This saved me a ton of time and tokens.

**1:06** · Another thing that makes the model so persistent are new reasoning levels above Extra High that give GPT-5.6 even more thinking power.

### Reasoning and subagents

**1:14** · If you're using the model in Codex, GPT-5.6 is better at delegating work to subagents.

**1:20** · Previous models could have access to that capability, but GPT-5.6 is trained to decide for itself when delegation is useful.

**1:28** · With our game, the model used subagents to break the work up and finish it in parallel, like art and sound design.

### GPT-5.6 in the API

**1:35** · If you're using GPT-5.6 in the API, we have a flagship model for ambitious agentic work, a more balanced model, and our fast, affordable model for everyday tasks.

**1:46** · This game is just one of many projects I've built with GPT-5.6, and I can't wait to see what you make.

**1:53** · Happy building.