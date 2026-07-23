![](https://www.youtube.com/watch?v=OYvlznJ4IZQ)

Engineers need to communicate effectively when building AI Systems.  
  
These terms will help you use a shared vocabulary. This is useful when discussing concepts, reading papers, or collaborating with teammates.  
  
Listed in order.  
00:00 Agenda  
00:28 1. Large Language Model  
01:28 2. Tokenization  
02:53 3. Vectorization  
04:15 4. Attention  
07:22 5. Self-Supervised Learning  
12:07 6. Transformer  
14:32 7. Fine-tuning  
17:05 8. Few-shot Prompting  
18:11 9. Retrieval Augmented Generation  
20:33 10. Vector Database  
23:03 11. Model Context Protocol  
25:43 12. Context Engineering  
28:17 13. Agents  
29:19 14. Reinforcement Learning  
34:42 15. Chain of Thought  
35:55 16. Reasoning Models  
36:36 17. Multi-modal Models  
38:21 18. Small Language Models  
40:24 19. Distillation  
41:47 20. Quantization  
  
If you are a software engineer looking to transition to AI, click the link below.  
AI Engineering Course: https://interviewready.io/course-page/ai-engineering  
  
#AI #SoftwareEngineering #Agents

## Transcript

### Agenda

**0:00** · Hi everyone, this is GKCS.

**0:01** · In today's video we will see some of the commonly used terms in the AI space.

**0:05** · If you are an engineer who is building applications, then you will find these terms useful.

**0:09** · When communicating with people within your team or outside.

**0:12** · And I think if you know these terms, then it is also easier to learn the deeper subjects around AI.

**0:18** · So by the end of this video, you'll have a list of terms whose definitions you understand quite well.

**0:22** · And I'll also be linking some references in the description so that you can dig into them further.

**0:26** · Let's start.

### 1\. Large Language Model

**0:28** · The first term that you should know about is large language model.

**0:35** · Also known as LM.

**0:38** · And the definition of this is a neural network.

**0:43** · That is trained to predict the next term.

**0:49** · Of an input sequence.

**0:54** · For example, if I pass in the query all that glitters to a large language model, then it's going to come up with the response of is not going okay.

**1:09** · At which point the complete response of all that glitters is not gold is returned to the user.

**1:15** · What do we mean by training?

**1:17** · What do we mean by neural network?

**1:19** · As we go through this video, you will be understanding these terms better one by one.

**1:24** · Okay.

**1:24** · The second term that we're looking at is tokenization.

### 2\. Tokenization

**1:29** · This has to do with processing the input of a large language model.

**1:32** · For example, if all that glitters is passed into a large language model, the first thing it's going to do is break this into discrete tokens.

**1:42** · That is the process of tokenization.

**1:44** · The first token will be all.

**1:46** · Then there's a space character.

**1:48** · You have then that after which you have glitched.

**1:53** · And finally also you might think, well, why shouldn't you just break this into space characters and get the job done?

**2:00** · The humans do not talk like that.

**2:02** · We are, after all, trying to process natural language.

**2:04** · So ours is a common term.

**2:07** · Shimmers. Murmurs. Flickers.

**2:09** · These are terms which have the suffix of ers which means that the action of glitched is being performed by that object.

**2:18** · Another example of this is in.

**2:22** · So eating, dancing, singing all have the suffix of ING, and a large language model can look at this token of ING and know that the previous action is being performed.

**2:35** · As long as you have the suffix.

**2:36** · Okay, remember, the core problem for the large language model is to truly understand human language so that it can speak it really well.

**2:43** · Tokenization is an essential part of that.

**2:46** · Whose end result is that the input text is broken into tokens.

### 3\. Vectorization

**2:53** · Which brings us to our third term vectors.

**2:59** · Tokens tell you what you should focus on.

**3:02** · What is the smallest term that you can derive meaning from?

**3:06** · But what meaning has to be derived is represented by vectors.

**3:11** · If the large language model can map a two dimensional or a n dimensional space.

**3:21** · Such that all the words which are close in meaning are placed close to each other, then the benefit will be that the meaning of these words will be turned into a coordinate.

**3:30** · In this n dimensional space.

**3:32** · This is called a vector.

**3:35** · Okay.

**3:36** · The coordinate.

**3:36** · The mapping of a word in a n dimensional space such that.

**3:41** · Nearby words.

**3:42** · Similar meaning words are all clustered together and opposite meaning words are somewhere far away.

**3:47** · Comes through the process of vectorization.

**3:52** · The end result of this is that large language models know the inherent meaning of all the words that are in the English vocabulary, and they also know how to break it into small tokens.

**4:02** · Any input text into tokens.

**4:04** · Words which are similar to each other are placed close to each other.

**4:08** · Once they know the meaning, they can construct sentences effectively.

### 4\. Attention

**4:15** · Okay, so now you have large language models which can tokenize input text, convert them into vectors.

**4:22** · But there is one major challenge which actually change the entire industry here, which made large language models very popular.

**4:29** · And that is attention.

**4:36** · We just said that all the input tokens for a large language model are converted into vectors.

**4:40** · The vectors encapsulate the meaning of those words.

**4:43** · But what about the word apple when you say it is a tasty apple, you mean the fruit, the edible apple?

**4:54** · When you say apples revenue, you probably mean the company.

**5:00** · And if you say the apple of my eye, you are probably talking about a young person who you have affection for.

**5:08** · So Apple has different meanings, and the only way to understand the meaning is not by looking at the word itself, because that spelling is the exact same, but by looking at nearby words which add context to the meaning of apple.

**5:28** · The moment I said tasty, you know that it's some sort of food that is going to talk about.

**5:33** · That's how humans derive meaning, and large language models can derive meaning this way.

**5:38** · Now, the way they do this is look at nearby words in a sentence.

**5:43** · Generate those vectors so nearby contextual vectors are picked up.

**5:52** · And for ambiguous terms you end up with ambiguous vectors.

**5:59** · But you can derive the exact meaning by adding this nearby contextual vector to it.

**6:04** · So take the vector of Apple.

**6:07** · Take the vector of revenue when you add these two vectors.

**6:11** · When you perform some sort of an operation, it's not a direct addition, but it's the attention operation.

**6:19** · You effectively take the vector of Apple and you push it in the direction of the company Apple.

**6:24** · So Google meta, Microsoft are all here.

**6:30** · The first operation of vector revenue is going to send it there.

**6:33** · If you instead add a vector of tasty, do this.

**6:37** · If you perform the attention mechanism of these two vectors, then it's going to push the vector of apple to banana, chiku and guava.

**6:45** · Okay, so you can tokenize input text.

**6:48** · You can derive the inherent meaning of all of those tokens.

**6:51** · And for ambiguous tokens, for tokens which are difficult to understand.

**6:54** · You have a mechanism to add context by looking at nearby words.

**6:59** · And this is another breakthrough that large language models have made.

**7:03** · This was in 2017.

**7:04** · The paper came out then, but in 2022 this became really, really famous which are gpt2 being released.

**7:10** · The quality of responses of a large language model far exceed anything else that we have seen earlier.

**7:15** · Okay, because it is able to derive contextual meaning, it's able to construct sentences in a way that humans speak.

### 5\. Self-Supervised Learning

**7:22** · Okay, so now we know how LMS can process input.

**7:30** · But how do you train them to predict the next token?

**7:36** · Okay, here's where there was a major breakthrough in 2017.

**7:41** · Basically the concept of self-supervised learning.

**7:48** · Became very popular.

**7:51** · Self-supervised learning means that instead of telling the model exactly what it needs to do, the structure of the input data is such that the model knows what it should do.

**8:03** · Okay.

**8:03** · For example, you're watching this video right now.

**8:06** · I'm going to make a part of this video blank.

**8:09** · So 12345.

**8:17** · What do you think is being hidden right now?

**8:20** · What number is coming to your mind?

**8:23** · Let's see if that is right.

**8:25** · Yes, most of you guessed one because we went in the sequence five, four, three, two, one.

**8:34** · Okay.

**8:34** · But when it comes to a video, you can also do something else.

**8:37** · Let me make another part of the video blank right now.

**8:42** · Where do you think the other AI is looking?

**8:46** · Let's check.

**8:48** · Most of you got it right.

**8:49** · Both eyes are looking upwards.

**8:52** · So what's happening is a section of the input can be predicted.

**8:57** · Even if you make that section blank, which means that there is inherent structure.

**9:05** · In your input which your mind is able to replace with the expected token or expected output.

**9:17** · Now, the standard way to train such a model would be called supervised learning, where you would have a human being say that if the input text is all that glitters, then the model should predict is not gold.

**9:32** · If the input text is at two, then the output should be Brutus instead.

**9:40** · Self-supervised learning has made getting test data much cheaper here.

**9:46** · If you have a two Brutus, then the model is going to be fed in this text and it's going to make three predictions. One, what comes after it?

**10:01** · Two what comes after a two and three what comes after it?

**10:06** · Two Brutus okay, no, humans are involved.

**10:11** · You had some text in the world.

**10:12** · Maybe you scraped this off the internet and now you're taking the model.

**10:16** · Look, I have three questions for you.

**10:17** · Tell me, what are the right answers?

**10:19** · So the model looks at these three puzzles.

**10:21** · They are all running in parallel, and they try to make predictions.

**10:25** · So it the model might say now the model might say two.

**10:30** · The model might say something, but you train the model that two is the expected response.

**10:36** · So if it makes a mistake then you penalize the model that increases loss.

**10:42** · And so the neural network weights are updated.

**10:45** · In the second task you have at two, if the model makes the prediction of Brutus, then you tell the model that this is great.

**10:53** · The weights don't need to be updated.

**10:55** · But if it says Caesar, then the model has to be penalized.

**11:00** · And so the internal weights are updated.

**11:03** · In the third case, if you predict a stop token like add to Brutus, that's it, then you will get it wrong.

**11:11** · If it is a comma, you're right.

**11:14** · And if it's, then maybe you're also right.

**11:18** · Okay.

**11:18** · What you're doing is you are looking at text, which already exists in the world, and you're creating multiple challenges for yourself without human intervention.

**11:27** · This is what makes the model self-supervised.

**11:31** · It might seem like a small thing, but this architectural decision or this benefit of the large language model makes it really, really scalable.

**11:39** · In fact, most AI models now are moving to self-supervised learning.

**11:43** · Even image models like we discussed, are looking for removing some patches of the image and trying to predict those patches.

**11:51** · The benefit of this is you understand the underlying structure and the inherent meaning of those patches.

**11:57** · In the case of text, it's going to be terms.

**11:59** · In the case of images, they are a bunch of pixels.

**12:02** · And in the case of video you might understand how an object even moves.

### 6\. Transformer

**12:07** · Okay.

**12:07** · So that explains what self-supervised learning is.

**12:11** · Next is the transformer okay.

**12:15** · And most people confuse transformer with large language model, which is completely understandable actually.

**12:21** · But that's not the case.

**12:22** · A large language model is something which predicts the next token given an input sequence.

**12:28** · A transformer does the exact same thing, but it's a specific algorithm or a specific method by which you predict the next token.

**12:35** · A transformer basically is input tokens.

**12:41** · Being run through an attention block, which is then forwarded to a neural network, a feedforward neural network, and then you have a bunch of outputs.

**12:53** · Okay, you can think of these as output vectors.

**12:56** · These vectors are then passed in to another layer of attention.

**13:01** · The first layer of attention, like we said, disambiguate terms.

**13:04** · The second layer might find more complex relationships.

**13:07** · It might find sarcasm. It might find implications.

**13:10** · For example, a crane was hunting a crab.

**13:13** · So in the first case you understood it is not the metal plane, it's a bird train.

**13:18** · But in the second one you might infer that the crab is fearful.

**13:22** · You might understand the crane is hungry.

**13:25** · So this is the second layer.

**13:27** · And then you have another feedforward neural network and so on.

**13:31** · Till finally you are confident enough to generate an output.

**13:35** · Okay. So you have these stacked.

**13:36** · Sometimes they're stacked to 12 layers, sometimes more.

**13:39** · I think recent GPT architectures are in hundreds.

**13:44** · The main idea behind this is are getting all of the meaning from your input tokens and then manipulating them again and again to finally predict what the next word should be.

**13:56** · This attention lock is order in square.

**13:59** · Okay.

**14:00** · You could replace this transformer in a large language model with something else to model.

**14:05** · A new architecture could come in, in which case the transformer and the state space models are gotten rid of, which could be a diffusion model.

**14:14** · That constructs essays or text.

**14:18** · Okay, so the large language model is actually the product.

**14:20** · You can think of it as a car.

**14:22** · And this is the engine.

**14:24** · A car, many people say is just the engine.

**14:26** · But no, there are some other fancy things around it.

**14:29** · The internal algorithm can be different.

### 7\. Fine-tuning

**14:32** · This term number seven, it's fine tuning.

**14:38** · We said that a large language model is something that is trained to predict the next term.

**14:46** · Of an input sequence.

**14:48** · The question is what type of next token are we talking about?

**14:52** · If you are talking about a medical large language model, something which helps doctors explain the diagnosis of a patient, then you're probably going to be thinking of medical terms.

**15:01** · If you have a model which is trained on financial operations.

**15:05** · Then the same model for the same query is going to think in terms of financial terms.

**15:10** · So the next token that the model comes up with is not always going to be general.

**15:15** · You're first going to train your base model.

**15:20** · In a self-supervised fashion.

**15:22** · Then you're going to take that model and make it go through a series of questions and answers.

**15:31** · This process is called fine tuning.

**15:36** · And goes something like who is the president of USA?

**15:42** · Donald Trump?

**15:45** · But the model could also say, I would like to know that too.

**15:53** · Here's where things are going wrong okay.

**15:55** · The model should not be responding like this.

**15:57** · Give us a direct answer or confess that you do not know.

**16:03** · Or you could say no.

**16:04** · But then this is also very, very bad because the models are trained to be helpful.

**16:10** · Okay, so what's happening is other plausible responses which are not wrong but are not desirable, are penalized in the fine tuning process.

**16:22** · You have these questions and answers.

**16:24** · The fine tuning process forces the model to take a question and give answers.

**16:30** · As expected.

**16:32** · So when it comes to a medical diagnosis, the model is going to train itself.

**16:36** · The internal weights will be updated in such a way that it will learn to speak in medical jargon or medical terms.

**16:44** · And so this step, where a base model is trained to answer in a specific way, is called fine tuning.

**16:51** · The same base model can be run through different sets of questions answers to come up with multiple fine tuned models.

**16:57** · So the base model of Lamarck can be fine tuned by a company to answer that customer's specific queries.

### 8\. Few-shot Prompting

**17:05** · A few short prompting.

**17:11** · So the main idea behind future prompting is before you send a query to a model, before you send a plain vanilla query to a large language model and ask it to come up with a response.

**17:25** · You augment the query.

**17:26** · You add more information by saying, look, if the query is where is my parcel?

**17:36** · Then let me tell you that there are some examples that I want you to go through.

**17:40** · This is happening during inference time during response time in production.

**17:44** · Right?

**17:44** · Life, your system, your server sends the original query and sends examples to the model so that it takes this into context and then gives an appropriate response.

**17:59** · The quality of the response goes up.

**18:01** · This is called future prompting.

**18:02** · It's basically example prompting example in prompt.

**18:08** · That's it.

### 9\. Retrieval Augmented Generation

**18:13** · It brings us to point number nine which is very interesting and is completely exploded, which is retrieval, augmented generation.

**18:24** · In fact, the AI space is moving so quickly that people are saying rank or retrieval augmented generation is already dead.

**18:32** · So the basic idea again, is that you have a large language model and you pass in the input from the server.

**18:41** · So a customer connects to you here they hit your API.

**18:45** · The server says, you know what this is the customer query that is forward that to the language model.

**18:49** · Along with that let's give some examples.

**18:51** · So that's for short prompting.

**18:53** · And along with that, since there are some company policies that I want you to know of, last language model, I'll give you those documents.

**19:03** · So in real time the server goes fetches the most relevant documents.

**19:07** · Maybe your policy document, maybe your terms and conditions.

**19:13** · When placing an order, and maybe many more things.

**19:16** · Right?

**19:17** · You send these documents along with examples of how you should respond.

**19:21** · This gives you a good idea of the format of the response.

**19:24** · This gives you a good idea of the company specific context, and this is the direct user input query.

**19:31** · Okay, with all of this, the large language model tends to give very high quality responses.

**19:39** · Now the question is where are you getting these documents from?

**19:41** · How does the server know which documents are related to which query?

**19:44** · There are many ways to do this.

**19:45** · If you talk to Neo Forger, which is a graph database company, they will tell you you should store things in a graph. DB.

**19:52** · If you talk to neon, then they will tell you that you should store things in a vector DB and some people will say just keep everything in memory.

**20:00** · Just keep everything in cache.

**20:02** · This doesn't matter how you fetch the documents, doesn't matter so much.

**20:05** · Usually it's a vector DB by the way, because.

**20:08** · But I mean it is easier to find relevant documents because you just do a similarity search.

**20:14** · Once you have the documents, you pass that to a large language model.

**20:18** · The large package model converts it internally into vectors and then gives you a response.

**20:23** · Okay, but at a high level you just want to add more and more context.

**20:28** · You retrieve the context, augment the query, and then generate a response.

### 10\. Vector Database

**20:34** · The 10th term, which is vector database.

**20:39** · We just mentioned vector database is something which is used to find relevant documents for an incoming query.

**20:45** · Let's see how that happens.

**20:48** · You have the request.

**20:49** · I am upset with your payment system.

**20:57** · I expect a refund.

**21:01** · This is a lot of terms in this query.

**21:03** · A human being can read this and easily understand what the user is feeling.

**21:07** · They are feeling upset.

**21:08** · I mean they've already mentioned it, but they are looking for a refund if you give them a refund, maybe the upset feeling will go away.

**21:16** · What do you do?

**21:17** · Which documents do you search for?

**21:19** · You could search for all documents where the word upset exists, but maybe you do not have it in your company policy.

**21:26** · Maybe nowhere is it mentioned that a user is upset, but you have a document which mentions if the user is giving you a low rating, or if a user drops off.

**21:40** · How do you make that decision that upset as a word, is close to the low rating or drop off?

**21:48** · We spoke about vectors.

**21:49** · Vectors can encapsulate semantic meaning, which means documents which store similar words are going to be similar or close in distance.

**21:59** · Remember, vectors are basically coordinates, right?

**22:02** · So the distance between upset and documents having low rating are going to be low.

**22:07** · You will fetch the documents which mention low rating or drop offs and use them to add context to your large language model.

**22:15** · When you have an incoming query from the user.

**22:20** · You're going to find which document is closest to the query and add that to the large language models context.

**22:28** · So this document will be sent along with the original user query and maybe a system prompt.

**22:38** · Where are you going to store these documents in a vector database, which helps you perform these similarity searches efficiently.

**22:48** · Some of these algorithms are hierarchical, navigable, small world.

**22:50** · We have spoken about this in detail in the interview.

**22:53** · Right course at the end of the day.

**22:56** · The vector database is like a black box to you.

**22:58** · You can store documents and you can quickly retrieve them when you need them.

### 11\. Model Context Protocol

**23:04** · Great.

**23:04** · So you can store internal company documents and information in a vector database to get context for a large language model.

**23:12** · But what if the context exists outside your system?

**23:17** · So this challenge was met with model context protocol.

**23:24** · Okay.

**23:24** · As the name suggests, it's a protocol or a way to communicate the transfer context into a model.

**23:34** · The basic idea here I made a detailed video on this.

**23:36** · You can check it out, but the basic idea here is that you have a large language model which, before receiving an incoming query from a user.

**23:49** · Has a client, an MCP client model, context protocol client which forwards the initial query user query.

**23:58** · The LLM now makes a decision.

**24:01** · It says that there may be external tools or databases that I want to connect to.

**24:07** · The client gets to know of this and connects with external MCP servers.

**24:14** · In one case, that might be Indigo.

**24:19** · In another case that will be Air India, whose MCP server can give you details around Air India.

**24:27** · So you can think of this as a wrapper for Air India's database.

**24:32** · This as a wrapper for Indigo's database.

**24:35** · As a response, you are going to get flight details.

**24:40** · From each of these airlines.

**24:44** · Once you have the details, you can forward it to the alum saying that hey, along with the user query and along with whatever system from the relevant context that I could get from my vector database, I'm also adding flight details, real time information from external servers, which you can now consume to come up with a decision.

**25:02** · Okay.

**25:02** · And the large language model at this point might say, okay, book flight number i.e. Indigo 1020, which then results in another API call to book on the MCP server of Indigo.

**25:18** · Okay.

**25:19** · The response final response is given to the MCP client.

**25:22** · The client then forwards it back to the user.

**25:25** · Result in customer satisfaction.

**25:27** · Okay.

**25:28** · You see that the user is no longer just able to get data up.

**25:31** · They do not have to do things themselves after being given the recipe.

**25:35** · The recipe can be completely executed by the MCP client.

**25:40** · Okay, so this makes LMS a lot more powerful.

### 12\. Context Engineering

**25:43** · MCP has picked up a lot of popularity now.

**25:46** · Okay, so all of this put together is called context engineering.

**25:54** · If you are an engineer, you have probably heard of this term.

**25:57** · And basically this is an encapsulation of many of the things that we have already discussed.

**26:02** · We discussed a few short prompting, which is giving examples.

**26:10** · We discussed retrieval, augmented generation, which is getting relevant documents from a vector database.

**26:19** · And using them to add context to a query and using model context protocol to hit external servers.

**26:30** · And perform actions as needed.

**26:34** · When it comes to context engineering.

**26:35** · This two new challenges that we are facing as engineers.

**26:39** · One is user preferences and the second is prompt summarization.

**26:52** · You can call it context summarization.

**26:57** · For example, you might use a sliding window.

**27:04** · Where the last 100 chats are sent directly to the large language model, and all the previous chats are summarized into five sentences, just.

**27:19** · This limits the max amount of chats that you are sending to the large language model.

**27:23** · You could use other techniques also.

**27:25** · For example, some people just focus on keywords.

**27:28** · Some people focus just on the last chat.

**27:30** · So one chat and the previous entire history summary together.

**27:35** · The idea is to get context summarization this way when you get a document, you again summarize it first and then send it.

**27:42** · So this can be done maybe using a cheap small language model or a distilled model.

**27:49** · And once you have generated the context, you send that to the expensive large language model.

**27:54** · You see, the main difference between context engineering and prompt engineering is prompt engineering is for one single prompt.

**28:00** · It is stateless.

**28:02** · Anytime you ask the large language model to behave in a particular way, the system prompt is going to be the same.

**28:06** · But context engineering evolves as per the user's declared preferences and also the previous chat history similar to what it was earlier, but this is more long term.

### 13\. Agents

**28:17** · Which brings us to the most long term thing you can come up with in the air space right now.

**28:22** · Agents.

**28:26** · I've taken a detailed video on this, so do check that out.

**28:28** · But at a high level, you have a long running process.

**28:35** · Which is known as an agent.

**28:37** · You can think of this is a server which is getting an API call.

**28:40** · And this has many capabilities.

**28:41** · It can go and query and LM.

**28:45** · It can also query external systems.

**28:51** · And other agents.

**28:55** · To meet the user's requirements.

**28:59** · Let's take an example here.

**29:00** · Let's say your travel agent can look into booking flights, booking hotels and even manage your email when you're away.

**29:09** · When it sees a window of opportunity.

**29:11** · Maybe the flights then are cheap.

**29:13** · It goes ahead and makes the booking according to your preferences.

**29:16** · All of this stuff can be managed by an agent and the most hyped term here.

### 14\. Reinforcement Learning

**29:25** · Is reinforcement learning.

**29:27** · It's a way in which you can train models to behave in a particular way.

**29:31** · So, for example, if you give a query a user query to the model, the model can generate two responses response one and response two.

**29:43** · You must have seen this in ChatGPT.

**29:45** · Choose the one which is better.

**29:48** · Okay, so the one which is chosen gets a plus one.

**29:50** · The other one gets a minus one.

**29:53** · What happened effectively is you took a user query.

**29:57** · This entire thing can be mapped to a vector.

**30:00** · And the vector is an n dimensional space.

**30:03** · So you go to that coordinate and you tell the model that look after reaching here you generated further tokens for the vectors.

**30:12** · So that's your path.

**30:13** · You went from here to here to here.

**30:15** · So this was the final point of response.

**30:18** · And now you got a score of plus one.

**30:21** · So this gets a score of plus one.

**30:23** · This also gets the score of plus one plus one plus one plus one plus one.

**30:28** · It's also discounting that you can do.

**30:29** · But for now let's just keep things simple.

**30:31** · This is a nice path.

**30:33** · You always want to follow this path.

**30:36** · Response two was bad there.

**30:39** · You followed this point to this point.

**30:43** · This point, and then you deviated.

**30:45** · The next token that you generated after the first three tokens, let's say, is not going.

**30:52** · And then you did a comma here and went, but it may be so token one, two, three for token one, two, three four. Okay.

**31:09** · This was bad.

**31:10** · It got a score of minus one, which means this area gets a score of minus one.

**31:15** · This also gets the score of minus one, minus one, minus one, minus one, plus one takes it to zero.

**31:23** · Minus one plus one takes it to zero.

**31:25** · Minus one plus one takes it to zero.

**31:28** · So what you're doing is you have a space where you have negative scores, positive scores and neutral scores.

**31:36** · If you do this enough, then you will end up with a space, a vector space where given an input query, given a starting point, you will have a space of negative where you do not want to go.

**31:48** · You will have a space of positive where you definitely want to go.

**31:52** · And the more positive it is, the more you want to go there.

**31:54** · Okay, so maybe you go here.

**31:56** · From here you have another very positive space which is over here.

**32:00** · This is like hill climbing, right?

**32:01** · You're basically trying to optimize on the path that you're taking as a large language model.

**32:08** · The expectation is that the final result will make the end user happy.

**32:13** · Okay.

**32:14** · If the end user experience is good, then the model is trained to make users happy.

**32:20** · That's what is reinforcement learning with human feedback.

**32:24** · Human feedback is telling you whether it is a plus 1 or -1, and the feedback is helping you reinforce good outputs.

**32:33** · This is an extremely powerful technique.

**32:35** · In fact, it is seen in nature.

**32:37** · If you know about Pavlov's dog, then there was this situation where Pablo would press a bell and give food to the dog when it would come after pressing the bell.

**32:47** · Eventually he realized that if he just presses the bell without giving food, the dog already comes and starts salivating because it's expecting food.

**32:55** · So its behaviors have been reinforced.

**32:58** · Fortunately, this is not the only capability that human beings have.

**33:01** · You cannot model human intelligence using just reinforcement learning.

**33:04** · I'll take an example.

**33:05** · Let's say you have a coin which is giving you heads.

**33:08** · Heads. Heads.

**33:09** · Heads. Heads. Heads.

**33:12** · If you know that this is a fair coin.

**33:13** · If you have a mental understanding of how the coin works, then what do you think is coming next?

**33:19** · Heads or tails?

**33:21** · Okay.

**33:22** · With what? Probability?

**33:25** · Okay, so I just looked at the camera and said, okay, okay.

**33:29** · Twice. Something's going on.

**33:32** · But as a human being, you should look at this and say if it is a fair coin, if it's an unbiased coin, then it can be heads or tails.

**33:42** · You can't guarantee that it is going to be heads next.

**33:45** · But reinforcement learning looks.

**33:47** · It observes the real world and based on that makes a decision.

**33:51** · So when it predicts heads it gets reinforced.

**33:54** · Great job.

**33:55** · When it predicts tails, it gets punished.

**33:58** · Bad job.

**33:59** · But the reality is this is a fair coin.

**34:02** · So there's a 5050 chance of either.

**34:06** · If you ask a human being, you show them the coin.

**34:08** · You tell them that this is a fair coin, and then you just keep flipping the coin.

**34:11** · You get a lot of heads.

**34:12** · They're just going to say 5050 because they have an internal representation of how the coin works.

**34:16** · They have a mental model of the physics of the coin.

**34:20** · While reinforcement learning cannot build mental models, they can just tell you based on outcomes what is more likely and what is maybe a more beneficial path.

**34:29** · Okay, we are not crocodiles. We are humans.

**34:31** · We have a deeper understanding of how things work.

**34:34** · Having said that, reinforcement learning is a powerful technique.

**34:36** · It does make models get smarter.

**34:40** · Quite smart right?

### 15\. Chain of Thought

**34:43** · Chain of thought.

**34:47** · Pretty simple concept, but very powerful.

**34:49** · When training the model, we clearly explain our thought process here.

**34:53** · The expectation is that as the model trains to break a problem step by step, it's going to look at newer problems with different parameters and still be able to reason through them because it has been trained to reason step by step.

**35:08** · This is called chain of thought, where the model goes through a series of deductions or inferences and comes up with the final response.

**35:17** · The quality of this response is usually much higher than a direct response.

**35:23** · As you can see, this is similar to a few short prompting.

**35:26** · The quality of the response is higher.

**35:28** · It has some examples to go through, but here the key difference is that there is a step by step breakdown, and new steps can be added by the model as it sees fit.

**35:38** · Because it is trained on so much training data, it may be able to reason to add more steps as the problem gets more and more difficult.

**35:44** · Okay.

**35:45** · In fact, this is something that has been seen by deep seek.

**35:48** · If you make the problem harder, it goes for more steps.

**35:51** · If you make the problem easy, then it goes for fewer steps.

### 16\. Reasoning Models

**35:55** · So this is called a reasoning model.

**36:03** · Okay.

**36:03** · They do not necessarily need to do chain of thought.

**36:05** · They can also use other algorithms.

**36:07** · For example there is tree of thought graph of thought also that you can go through.

**36:11** · You can use tools also to come up with better reasoning, but a model that can reason, a model that can figure out, given a problem, how to solve that problem step by step is a reasoning model.

**36:24** · This is also known as L or M's.

**36:27** · Okay, examples of this deep seek and OpenAI.

**36:32** · I mean the O one and O three another.

**36:34** · All these models but they newer models with new capabilities. Now multi model models. Okay.

### 17\. Multi-modal Models

**36:45** · So the basic idea is that most large language models that we know of operate on text.

**36:51** · But what about models which can accept and create images, generate images.

**37:00** · What about models which can accept and create videos. Okay.

**37:05** · So they can analyze images.

**37:06** · They can tell you the number of apples in an image, let's say.

**37:09** · Or they can modify an image to create a new image.

**37:13** · Similarly for video, these have tremendous application similar to how large language models have changed the marketing space.

**37:23** · To textual content.

**37:24** · Now, social media is rife with large language model content.

**37:28** · Images are going to get better and better, and video can be a really big deal.

**37:33** · Because if you have celebrities.

**37:38** · Who can create video?

**37:39** · You can create ads through large language models.

**37:41** · Then the cost expectation of creating video is going to go down okay.

**37:47** · This is already happening to some extent, but the quality of the models are not very good.

**37:50** · Multimodal in general means any kind of mode of input data.

**37:57** · It turns out that their performance is better than models which are just trained on text. Okay.

**38:01** · They have a deeper understanding of the meaning of objects.

**38:06** · If you train a model on cat and feline and so on, and then if you show it, images of cats, then the performance of the model, the output quality is usually better.

**38:18** · Okay.

**38:18** · The training is better.

### 18\. Small Language Models

**38:21** · Fine.

**38:21** · Let's get to three major topics, which is where the AI space is heading.

**38:27** · Okay.

**38:28** · People are looking for more company specific smaller models.

**38:31** · Foundation models.

**38:33** · The reason for this is companies want more control over what they generate.

**38:36** · They also want to keep the data close to themselves.

**38:38** · They don't want to expose it to any other third party company.

**38:41** · So one of the things which is happening is we are looking at smaller models.

**38:48** · Of small language models.

**38:51** · As you can expect with the words have fewer parameters than large language models.

**38:57** · For example, a small language model may have 3 million to 300 million parameters.

**39:01** · Okay, the neural network internally has fewer connections, fewer weights.

**39:06** · But if you look at large language models, contrast it.

**39:09** · You have 3 to 300 billion parameters.

**39:12** · So this is a very large neural network with a lot of weights in a LM.

**39:19** · But the SLM is smaller.

**39:22** · But they are useful because they are trained on lesser data, which can be company specific.

**39:33** · Or task specific.

**39:36** · For example, a bot which is trained on just customer queries, how to manage customer queries, how to make sales is likely to perform decently well.

**39:45** · Okay, it's going to be an expert at sales, but it probably can't tell you a detailed weather analysis.

**39:52** · For most companies, this doesn't matter.

**39:55** · In the case of NASA. This is what you need.

**39:57** · You are probably not selling anything openly, so maybe you are.

**40:00** · Who knows?

**40:01** · But NASA would be more interested in building a foundation model which can predict the weather, but not bothered about the sales part.

**40:10** · So in this way, smaller language models are being trained by companies on their specific data, on the proprietary data to come up with reasonably good responses for specific use cases.

### 19\. Distillation

**40:24** · And the process of building small language models is usually distillation.

**40:33** · The basic idea is you have a large language model, which is a teacher, and then you pass in some input.

**40:43** · You look at the output of the large language model, and in parallel you also send it to a small language model.

**40:51** · Okay, with fewer parameters.

**40:53** · You and it also tries to predict the output.

**40:57** · So the teacher produces an output and the student tries to mimic the teacher.

**41:05** · If these two outputs match, then the small language model is doing well.

**41:09** · No weights need to change, but if it is not doing well, then the internal weights of the small language model are changed.

**41:16** · But there is a limited number of weights assigned to this model 3 to 300 million.

**41:21** · What you are basically trying to do is condense this information, the the complex neural network, into the most reasonable representation that you can have such that your performance is okay, but the costs are significantly reduced.

**41:34** · So during runtime, during production inference time when you get a query, this is going to be much faster at responding as compared to this large language model.

**41:43** · It's also easier to host.

### 20\. Quantization

**41:48** · Okay.

**41:48** · Distilled models take us to the last term that you really should know if you are the engineer, and that is quantization.

**41:58** · Here the idea is that you have neural networks.

**42:03** · Each of these weights is basically a number, let's say a 32 bit number.

**42:11** · What if you could take these weights and condense that information into eight bits.

**42:19** · Then 75% of your memory is expected to be saved.

**42:23** · It doesn't directly map over here because the weights are usually just done on the feedforward neural network.

**42:28** · You still have the attention mechanism, and also the training cost is the same because initially you come up with a really good model with zero quantization.

**42:36** · Once the model is completely trained, that's when you apply quantization.

**42:39** · So the training cost does not reduce.

**42:41** · This is mainly to reduce inference cost or during production.

**42:46** · The cost of running a model.

**42:48** · So these are the most important 20 terms that I want to discuss in the engineering space.

**42:55** · I think knowing these terms will help you effectively communicate with any other engineer or people in the team.

**43:01** · I couldn't go into enough detail here because, I mean, when you're talking about the attention mechanism or quick action, you cannot do this in a 20 30 minute video.

**43:11** · But the things you should know about are these terms.

**43:14** · And also most of the things that are mentioned in the engineering course are going to be ready.

**43:19** · If you know them, then you truly understand how these models work.

**43:22** · And all of the hype and nonsense which is going on in this space, they become hype and nonsense to you, right?

**43:27** · You are able to recognize it much better. Thank you for watching.

**43:30** · I hope you enjoyed the video. I'll see you next time. Bye bye.