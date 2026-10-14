---
title: "Auto_Testing_Project_Overview"
source: "D:\\Projects\\Personal AI Memory\\data\\inbox\\Auto_Testing_Faculty_Explanation.pdf"
source_type: "pdf"
filename: "Auto_Testing_Faculty_Explanation.pdf"
generated_date: "2026-08-27T03:42:34.068652+00:00"
reading_time_minutes: 6
difficulty: "intermediate"
categories:
  - "Artificial Intelligence"
  - "Machine Learning"
  - "Natural Language Processing"
  - "Software Engineering"
  - "System Architecture"
keywords:
  - "auto testing"
  - "question-answering system"
  - "semantic retrieval"
  - "bm25"
  - "rrf"
  - "abstention gate"
  - "qwen3:8b"
  - "retrieval evaluation"
  - "frozen baseline"
  - "cross-encoder reranking"
tags:
  - "ai"
  - "machine-learning"
  - "nlp"
  - "software-engineering"
  - "system-architecture"
  - "llm"
  - "retrieval"
  - "evaluation-metrics"
processing_confidence: 0.90
---
<!-- PAM:BEGIN MANAGED -->
# Auto_Testing_Project_Overview

## Summary

Auto Testing is an intelligent question-answering system that combines semantic and keyword retrieval to provide evidence-based answers using a local LLM.

The Auto Testing project is an intelligent question-answering system that retrieves relevant information from a document collection and uses a local LLM to generate answers. The system combines semantic vector retrieval with BM25 keyword retrieval, fuses their results using RRF, applies confidence-based abstention, and generates answers through Qwen3:8B. It addresses LLM hallucinations by ensuring answers are grounded in retrieved evidence. The project includes automated testing, quantitative evaluation metrics, and frozen baselines for controlled development.

## Table of Contents

- [[#Reading Time|Reading Time]]
- [[#Difficulty Level|Difficulty Level]]
- [[#Keywords|Keywords]]
- [[#Categories|Categories]]
- [[#Tables|Tables]]
- [[#Key Concepts|Key Concepts]]
- [[#Definitions|Definitions]]
- [[#Important Entities|Important Entities]]
- [[#Related Topics|Related Topics]]
- [[#Suggested Related Notes|Suggested Related Notes]]
- [[#Suggested Backlinks|Suggested Backlinks]]
- [[#Frequently Asked Questions|Frequently Asked Questions]]
- [[#Flashcards|Flashcards]]
- [[#Multiple Choice Questions|Multiple Choice Questions]]
- [[#Short Answer Questions|Short Answer Questions]]
- [[#Long Answer Questions|Long Answer Questions]]
- [[#Revision Notes|Revision Notes]]
- [[#Tags|Tags]]
- [[#Metadata|Metadata]]
- [[#References|References]]

## Reading Time

**6 minutes**

## Difficulty Level

**Intermediate**

## Keywords

`auto testing`, `question-answering system`, `semantic retrieval`, `bm25`, `rrf`, `abstention gate`, `qwen3:8b`, `retrieval evaluation`, `frozen baseline`, `cross-encoder reranking`

## Categories

- Artificial Intelligence
- Machine Learning
- Natural Language Processing
- Software Engineering
- System Architecture

## Tables

| Metric | Current Result |
| --- | --- |
| Threshold | 0.45 |
| False Positive Rate (FPR) | 0.714 |
| False Negative Rate (FNR) | 0.000 |
| Negative rejection | 0.286 |
| Hit@5 | 0.953 |
| Recall@5 | 0.913 |
| Positive-only MRR | 0.930 |
| Passed | 1,398 |
| Deselected | 57 |
| Coverage | 89.29% |

## Key Concepts

- [[Hybrid Retrieval]] (high): Combines semantic vector retrieval and BM25 keyword retrieval to handle different types of queries effectively.
- [[Abstention Gate]] (high): Checks retrieval confidence before generating an answer. If confidence is insufficient, the system abstains from providing an answer.
- [[Reciprocal Rank Fusion (RRF)]] (high): A method to combine ranking results from different retrieval systems without requiring their scores to be calibrated to the same scale.
- [[Qwen3:8B]] (high): A local LLM used to generate final answers from retrieved context.
- [[Frozen Baseline]] (medium): A stable configuration used as a reference for evaluating changes in subsequent development phases.
- [[Cross-Encoder Reranking]] (medium): A second-stage relevance check applied to a smaller candidate set after initial retrieval to improve retrieval quality.
- [[Retrieval Evaluation Metrics]] (medium): Quantitative measures like Hit@5, Recall@5, MRR, FPR, FNR, and coverage used to assess retrieval quality.
- [[Semantic Retrieval]] (high): Uses vector embeddings to find documents or chunks with semantically similar meaning, even if the exact words don't match.
- [[Keyword Retrieval (BM25)]] (high): Traditional lexical retrieval method that finds documents based on exact terminology, names, or distinctive words.
- [[Answer Generation Pipeline]] (high): The process of retrieving evidence, fusing results, applying confidence checks, and using a local LLM to generate a final answer.

## Definitions

- [[Hybrid Retrieval]]: A retrieval strategy that combines semantic vector search and BM25 keyword search to handle both semantic and exact matching queries.
- [[Abstention Gate]]: A mechanism that checks if the retrieved evidence is sufficiently reliable. If not, the system refrains from generating an answer.
- [[Reciprocal Rank Fusion (RRF)]]: A method to combine ranking results from different retrieval systems without requiring their raw scores to be calibrated to the same scale.
- [[Qwen3:8B]]: A large language model used as the final answer generation component in the Auto Testing system.
- [[Frozen Baseline]]: A stable configuration used as a reference point for evaluating changes in subsequent development phases.
- [[Cross-Encoder Reranking]]: A second-stage relevance check applied to a smaller candidate set after initial retrieval to improve retrieval quality.
- [[Retrieval Evaluation Metrics]]: Quantitative measures used to assess the effectiveness of the retrieval process, including Hit@5, Recall@5, MRR, FPR, FNR, and coverage.
- [[Semantic Retrieval]]: A retrieval method that uses vector embeddings to find documents or chunks with semantically similar meaning, even if the exact words don't match.
- [[Keyword Retrieval (BM25)]]: A traditional lexical retrieval method that finds documents based on exact terminology, names, or distinctive words.
- [[Answer Generation Pipeline]]: The process of retrieving evidence, fusing results, applying confidence checks, and using a local LLM to generate a final answer.

## Important Entities

- [[Auto Testing Project]] (project): An intelligent question-answering system that combines semantic and keyword retrieval to provide evidence-based answers using a local LLM.
- [[Qwen3:8B]] (technology): A local LLM used to generate final answers from retrieved context.
- [[BM25]] (technology): A traditional lexical retrieval method that finds documents based on exact terminology, names, or distinctive words.
- [[Reciprocal Rank Fusion (RRF)]] (technology): A method to combine ranking results from different retrieval systems without requiring their scores to be calibrated to the same scale.
- [[Abstention Gate]] (technology): A mechanism that checks if the retrieved evidence is sufficiently reliable. If not, the system refrains from generating an answer.
- [[Cross-Encoder Reranking]] (technology): A second-stage relevance check applied to a smaller candidate set after initial retrieval to improve retrieval quality.
- [[Frozen Baseline]] (concept): A stable configuration used as a reference point for evaluating changes in subsequent development phases.
- [[Hit@5]] (concept): A retrieval evaluation metric that measures the proportion of queries where a relevant item appears in the top five results.
- [[Recall@5]] (concept): A retrieval evaluation metric that measures the proportion of relevant items retrieved within the top five results.
- [[Mean Reciprocal Rank (MRR)]] (concept): A retrieval evaluation metric that measures the average reciprocal rank of the first relevant item in the results.

## Related Topics

- [[Question Answering Systems]]: The project is an example of a question-answering system that combines retrieval and generation.
- [[Retrieval-Augmented Generation (RAG)]]: The system uses retrieval to provide evidence for LLM-generated answers.
- [[Hybrid Retrieval Systems]]: The project combines semantic and keyword retrieval methods.
- [[Abstention in AI Systems]]: The system includes a mechanism to abstain from answering when evidence is insufficient.
- [[Evaluation Metrics for Retrieval]]: The project uses quantitative metrics like Hit@5, Recall@5, and MRR to assess retrieval quality.
- [[Frozen Baselines in Software Development]]: The project uses frozen baselines to ensure changes can be evaluated independently.
- [[Cross-Encoder Reranking]]: The project includes a cross-encoder reranking component in the Phase 3C-B extension.
- [[LLM Answer Generation]]: The system uses a local LLM to generate final answers from retrieved context.
- [[Semantic Search]]: The system uses semantic vector retrieval for similarity-based document search.
- [[Keyword Search]]: The system uses BM25 for traditional lexical retrieval.

## Suggested Related Notes

- [[Question_Answering_Systems_Overview]]
- [[Retrieval-Augmented_Generation_Overview]]
- [[Hybrid_Retrieval_Systems_Overview]]
- [[Abstention_in_AI_Systems_Overview]]
- [[Evaluation_Metrics_for_Retrieval_Overview]]
- [[Frozen_Baselines_in_Software_Development]]
- [[Cross-Encoder_Reranking_Overview]]
- [[LLM_Answer_Generation_Overview]]
- [[Semantic_Search_Overview]]
- [[Keyword_Search_Overview]]

## Suggested Backlinks

- [[Question_Answering_Systems_Overview]]
- [[Retrieval-Augmented_Generation_Overview]]
- [[Hybrid_Retrieval_Systems_Overview]]
- [[Abstention_in_AI_Systems_Overview]]
- [[Evaluation_Metrics_for_Retrieval_Overview]]
- [[Frozen_Baselines_in_Software_Development]]
- [[Cross-Encoder_Reranking_Overview]]
- [[LLM_Answer_Generation_Overview]]
- [[Semantic_Search_Overview]]
- [[Keyword_Search_Overview]]

## Frequently Asked Questions

**Q1: Why not use only an LLM?**
A1: Because an LLM may hallucinate or use information outside the intended document corpus. Retrieval provides evidence and the abstention gate can reject weak cases.

**Q2: Why use both vector search and BM25?**
A2: They solve different retrieval problems: semantic similarity versus exact lexical matching.

**Q3: Why RRF?**
A3: It provides a simple way to combine rankings from different retrieval systems without requiring their raw scores to be calibrated to the same scale.

**Q4: Why abstention?**
A4: To avoid producing an answer when the system does not have sufficient evidence.

**Q5: What is reranking?**
A5: It is a second-stage relevance check applied to a smaller candidate set after first-stage retrieval.

**Q6: How do you know the system works?**
A6: Through automated tests and quantitative evaluation such as Hit@5, Recall@5, MRR, FPR, FNR and coverage.

**Q7: What is your baseline?**
A7: The Phase 3B frozen configuration, including the 0.45 abstention threshold and its recorded evaluation metrics.

**Q8: What makes this more than a simple chatbot?**
A8: The answer is grounded in a retrievable document corpus, with two independent retrieval signals and explicit evidence fusion.

**Q9: Why hybrid retrieval?**
A9: Semantic retrieval is strong when the question and source use different wording but have the same meaning. BM25 is strong when exact words and terminology are important.

**Q10: What is the main objective of the project?**
A10: To retrieve the most relevant information from the document collection, combine semantic and keyword retrieval, reduce unsupported answers, use a local LLM to generate answers, and measure retrieval quality through automated tests.

## Flashcards

**Card 1 - Front:** What is the main objective of the Auto Testing project?
**Back:** To retrieve the most relevant information from the document collection, combine semantic and keyword retrieval, reduce unsupported answers, use a local LLM to generate answers, and measure retrieval quality through automated tests.

**Card 2 - Front:** Why use both semantic and keyword retrieval?
**Back:** They solve different retrieval problems: semantic similarity versus exact lexical matching.

**Card 3 - Front:** What is the purpose of the Abstention Gate?
**Back:** To avoid producing an answer when the system does not have sufficient evidence.

**Card 4 - Front:** What is Reciprocal Rank Fusion (RRF)?
**Back:** A method to combine ranking results from different retrieval systems without requiring their scores to be calibrated to the same scale.

**Card 5 - Front:** What is the role of Qwen3:8B in the system?
**Back:** It is used to generate the final answer from retrieved context.

**Card 6 - Front:** What is a Frozen Baseline?
**Back:** A stable configuration used as a reference point for evaluating changes in subsequent development phases.

**Card 7 - Front:** What is the current abstention threshold?
**Back:** 0.45

**Card 8 - Front:** What are the evaluation metrics used for retrieval?
**Back:** Hit@5, Recall@5, MRR, FPR, FNR, and coverage.

**Card 9 - Front:** What is the purpose of reranking in Phase 3C-B?
**Back:** To score candidate query-document pairs more directly than first-stage retrieval.

**Card 10 - Front:** What is the main difference between retrieval and reranking?
**Back:** Retrieval quickly produces a candidate set, while reranking performs a more expensive relevance assessment on those candidates.

## Multiple Choice Questions

**1. Why does the Auto Testing project use hybrid retrieval?**
   A. [ ] To reduce development time
   B. [X] To handle both semantic and exact matching queries
   C. [ ] To increase system complexity
   D. [ ] To make the system more user-friendly
   *Explanation: Hybrid retrieval combines semantic vector search and BM25 keyword search to address different retrieval problems: semantic similarity versus exact lexical matching.*

**2. What is the primary purpose of the Abstention Gate?**
   A. [ ] To speed up the answer generation process
   B. [X] To ensure the system only answers when evidence is sufficient
   C. [ ] To improve the accuracy of the LLM
   D. [ ] To reduce the number of queries
   *Explanation: The Abstention Gate checks if the retrieved evidence is sufficiently reliable. If not, the system refrains from generating an answer.*

**3. Which metric indicates the proportion of queries where a relevant item appears in the top five results?**
   A. [ ] Recall@5
   B. [ ] Hit@5
   C. [ ] MRR
   D. [ ] FPR
   *Explanation: Hit@5 measures the proportion of queries where a relevant item appears in the top five results.*

**4. What is the role of Reciprocal Rank Fusion (RRF) in the system?**
   A. [ ] To generate the final answer using the LLM
   B. [ ] To score candidate query-document pairs more directly
   C. [X] To combine ranking results from different retrieval systems
   D. [ ] To provide a frozen baseline for evaluation
   *Explanation: RRF is used to combine ranking results from different retrieval systems without requiring their raw scores to be calibrated to the same scale.*

**5. Which of the following is a key component of the Auto Testing project's architecture?**
   A. [ ] A single-stage retrieval system
   B. [X] A cross-encoder reranking component in Phase 3C-B
   C. [ ] A system that only uses keyword retrieval
   D. [ ] A system that does not use any evaluation metrics
   *Explanation: The project includes a reranking stage under Phase 3C-B with a CrossEncoderReranker component.*

**6. What is the main advantage of using a frozen baseline in the project?**
   A. [ ] To reduce development costs
   B. [X] To allow changes to be evaluated independently
   C. [ ] To increase system complexity
   D. [ ] To make the system more user-friendly
   *Explanation: Frozen baselines provide a stable reference for evaluating changes in subsequent development phases.*

**7. What is the primary function of the Qwen3:8B model in the system?**
   A. [ ] To perform semantic retrieval
   B. [X] To generate the final answer from retrieved context
   C. [ ] To score candidate query-document pairs
   D. [ ] To perform BM25 keyword search
   *Explanation: Qwen3:8B is used as the final answer generation component in the Auto Testing system.*

**8. Which of the following is a retrieval evaluation metric?**
   A. [ ] Precision
   B. [ ] Accuracy
   C. [X] Hit@5
   D. [ ] Confidence
   *Explanation: Hit@5 is a retrieval evaluation metric that measures the proportion of queries where a relevant item appears in the top five results.*

**9. What is the purpose of the Phase 3C-B extension in the project?**
   A. [ ] To replace the entire retrieval pipeline
   B. [X] To add a cross-encoder reranking component
   C. [ ] To remove the need for evaluation metrics
   D. [ ] To simplify the system architecture
   *Explanation: The Phase 3C-B extension includes a CrossEncoderReranker component for more precise relevance assessment.*

**10. What is the main difference between retrieval and reranking in the system?**
   A. [ ] Retrieval is faster but less accurate than reranking
   B. [X] Reranking is a second-stage relevance check applied to a smaller candidate set
   C. [ ] Retrieval and reranking use the same scoring method
   D. [ ] Reranking is only used for keyword-based queries
   *Explanation: Retrieval quickly produces a candidate set, while reranking performs a more expensive relevance assessment on those candidates.*

## Short Answer Questions

**1. What is the main problem the Auto Testing project aims to solve?**
*Answer: The main problem is that an LLM can generate answers even when it does not have reliable evidence, leading to hallucinations or irrelevant answers.*

**2. What are the two main types of retrieval methods used in the system?**
*Answer: The two main retrieval methods are semantic vector retrieval and BM25 keyword retrieval.*

**3. What is the purpose of the Abstention Gate?**
*Answer: The Abstention Gate checks if the retrieved evidence is sufficiently reliable. If not, the system refrains from generating an answer.*

**4. What is Reciprocal Rank Fusion (RRF) used for in the system?**
*Answer: RRF is used to combine ranking results from different retrieval systems without requiring their raw scores to be calibrated to the same scale.*

**5. What is the role of the Qwen3:8B model in the system?**
*Answer: The Qwen3:8B model is used to generate the final answer from retrieved context.*

**6. What is the current abstention threshold in the system?**
*Answer: The current abstention threshold is 0.45.*

**7. What is the purpose of the Frozen Baseline in the project?**
*Answer: The Frozen Baseline provides a stable reference for evaluating changes in subsequent development phases.*

**8. What is the main advantage of using hybrid retrieval?**
*Answer: Hybrid retrieval allows the system to handle both semantic and exact matching queries effectively.*

**9. What is the primary function of the Cross-Encoder Reranking in Phase 3C-B?**
*Answer: Cross-Encoder Reranking is used to score candidate query-document pairs more directly than first-stage retrieval.*

**10. What is the main benefit of using quantitative evaluation metrics?**
*Answer: Quantitative evaluation metrics allow the system's performance to be measured and improvements to be tracked.*

## Long Answer Questions

**1. Explain the Auto Testing project's architecture and how it addresses the limitations of traditional LLM-based question-answering systems.**

The Auto Testing project's architecture combines semantic vector retrieval with BM25 keyword retrieval to handle both semantic and exact matching queries. The system uses Reciprocal Rank Fusion (RRF) to combine the results of these retrieval methods. An Abstention Gate checks if the retrieved evidence is sufficiently reliable before generating an answer. This approach addresses the limitations of traditional LLM-based systems by ensuring answers are grounded in retrieved evidence, reducing hallucinations and irrelevant answers. The system also includes automated testing and quantitative evaluation metrics to ensure reliability and measurable improvements.

**2. Describe the role of the Abstention Gate in the Auto Testing project and why it is important for the system's functionality.**

The Abstention Gate in the Auto Testing project checks if the retrieved evidence is sufficiently reliable. If the confidence level is too low, the system refrains from generating an answer to avoid producing unsupported responses. This mechanism is crucial because it prevents the system from providing answers based on insufficient or unreliable evidence, thereby improving the accuracy and reliability of the system's outputs.

**3. How does the system handle the combination of semantic and keyword retrieval results, and what is the role of Reciprocal Rank Fusion (RRF) in this process?**

The system combines the results of semantic vector retrieval and BM25 keyword retrieval using Reciprocal Rank Fusion (RRF). RRF is a method that merges ranking evidence from different retrieval systems without requiring their scores to be calibrated to the same scale. This allows the system to effectively integrate both semantic and exact matching results, improving the overall quality and relevance of the retrieved information.

**4. What are the key benefits of using frozen baselines in the development of the Auto Testing project, and how do they contribute to the system's reliability?**

Frozen baselines in the Auto Testing project provide a stable reference point for evaluating changes in subsequent development phases. This ensures that any improvements or regressions can be measured against a known baseline, allowing for controlled experimentation and reliable system evolution. By maintaining a consistent baseline, the project enhances the reliability and predictability of its development process.

**5. Explain how the system evaluates its retrieval quality and the importance of quantitative metrics in this process.**

The system evaluates its retrieval quality using quantitative metrics such as Hit@5, Recall@5, MRR, FPR, FNR, and coverage. These metrics provide a measurable way to assess the effectiveness of the retrieval process, ensuring that the system can be continuously improved. By tracking these metrics, the project can identify areas for enhancement and validate the success of any changes made to the system.

## Revision Notes

### System Architecture Overview

- User Query → Embedding + BM25 → Vector Search + BM25 Search → RRF Fusion (k=60) → Candidate Result → Abstention Gate → Context → Qwen3:8B → Final Answer

### Key Components

- Semantic Retrieval
- BM25 Keyword Retrieval
- RRF Fusion
- Abstention Gate
- Qwen3:8B
- Cross-Encoder Reranking (Phase 3C-B)

### Evaluation Metrics

- Hit@5
- Recall@5
- MRR
- FPR
- FNR
- Coverage

### Development Approach

- Incremental development through milestones
- Frozen baselines for stable reference
- Controlled changes with dedicated testing

### Project Objectives

- Retrieve relevant information from document collection
- Combine semantic and keyword retrieval
- Reduce unsupported answers
- Use local LLM for answer generation
- Measure retrieval quality through automated tests

### Why Hybrid Retrieval?

- Semantic retrieval handles different wording with same meaning
- BM25 handles exact terminology and identifiers
- Combines strengths of both methods

### Abstention Gate Importance

- Prevents generation of unsupported answers
- Improves system reliability
- Ensures answers are based on reliable evidence

### Reranking in Phase 3C-B

- CrossEncoderReranker component
- Second-stage relevance check
- More precise candidate evaluation

### Frozen Baseline

- Phase 3B is the frozen baseline
- Provides reference for evaluating changes
- Maintains stable configuration for development

### System Differentiation

- Grounded in retrievable document corpus
- Two independent retrieval signals
- Explicit evidence fusion
- Abstention mechanism
- Quantitative evaluation metrics

## Tags

- #ai
- #machine-learning
- #nlp
- #software-engineering
- #system-architecture
- #llm
- #retrieval
- #evaluation-metrics

## Metadata

- **Author:** Unknown
- **Word Count:** 1,150
- **Page Count:** 1
- **Language:** en
- **Source URL:** file:///D:/Projects/Personal AI Memory/data/inbox/Auto_Testing_Faculty_Explanation.pdf
- **Creation Date:** Unknown
- **Publisher:** Unknown
- **Version:** 1
- **License:** Unknown

## References

- Source: D:\Projects\Personal AI Memory\data\inbox\Auto_Testing_Faculty_Explanation.pdf
- Source type: pdf
- Original filename: Auto_Testing_Faculty_Explanation.pdf
- Generated date: 2026-08-27T03:42:34.068652+00:00
- Source title: Microsoft Word - Auto_Testing_Faculty_Explanation
- Author: Giridhar B M
- Processing Confidence: 90%

## Wiki Navigation

- [[index]]
- [[overview]]
- [[log]]
<!-- PAM:END MANAGED -->
