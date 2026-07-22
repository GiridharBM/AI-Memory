![](https://www.artificialintelligence-news.com/wp-content/uploads/2026/07/1784472098908.jpeg)

Enterprises evaluating Chinese open-weight models this month face a question that has nothing to do with benchmarks: whether using one will still be straightforward in a year. Moonshot AI’s Kimi K3 arrived on July 16 as the largest open-weight model yet released, and within days it had reopened a policy argument in Washington that had been dormant for a year.

The outcome will affect procurement decisions well outside the United States, because the mechanisms under discussion–federal procurement rules, export blacklists, security advisories–travel through the same cloud providers that serve most of the world. The immediate trigger was [a post](https://x.com/deanwball/status/2078133895766114412) by Dean W. Ball, OpenAI’s head of strategic futures and until recently a senior AI adviser in the Trump White House.

His assessment of the model was largely positive: a very good model, he wrote, whose performance he did not think could be explained away by distillation. He also observed that it seemed “very token hungry,” and that it was not obvious to him that it is actually cheap to run, a useful caution, given K3 launches with maximum reasoning effort as its only setting and bills output at $15 per million tokens.

Then he predicted that the Trump administration would eventually decide its best strategy was to create regulatory risk around Chinese open-weight models. Not a ban, which he called one of the dumber motifs in AI policy, but soft guidance from agencies suggesting such models may contain backdoors. “It needn’t be that well justified,” he wrote. Enough uncertainty, and regulated enterprises retreat on their own.

### Why Chinese open-weight models are a commercial problem first

The reaction was fierce, and it came from Americans rather than from Beijing. David Sacks, co-chair of the President’s Council of Advisors on Science and Technology, said he could not tell whether Ball was confessing to a regulatory capture strategy or predicting one, and that either way, weaponising regulatory uncertainty as a competitive tool should be unacceptable.

He added that the leading closed labs, already a duopoly in model revenue, want the government to remove their open-source competition. Yann LeCun and Martin Casado argued that open and proprietary development can coexist. Ball later clarified that he had been forecasting rather than recommending, and walked back the claim that open weights necessarily slow the field down.

Underneath the personalities is an arithmetic problem. Closed labs need revenue per token to justify the capital they are raising for data centres, and cheaper open-weight models compress that revenue without reducing how much AI gets used, the point Snorkel AI co-founder Braden Hancock put to *[TechCrunch](https://techcrunch.com/2026/07/20/openai-is-scared-of-open-weight-models-should-the-us-be/)*. The routing data already shows the shift: open-weight models handled 29% of tokens through Vercel’s production gateway in June, up from roughly a ninth in April, while accounting for under 4% of spending.

That pressure is arriving from inside the American stack. GitHub made Moonshot’s Kimi K2.7 Code [generally available](https://github.blog/changelog/2026-07-01-kimi-k2-7-is-now-available-in-github-copilot/) in the Copilot model picker on July 1, hosted on Microsoft Azure. *The Information* reports Microsoft is now adding K3 to Azure and evaluating whether it can run Copilot features currently handled by OpenAI and Anthropic models, with potential inference savings of up to $600 million.

Microsoft has confirmed neither the figure nor which features. It is an evaluation, not a deployment, but it is the largest customer of both American frontier labs, pricing the alternative.

### The security argument, taken seriously

Commercial motive does not make the security concern fake, and the strongest version of it deserves stating. Open weights cannot be recalled. Once a model is downloaded and running inside thousands of organisations, no vendor can patch it, revoke it, or push a fix, which is a materially different risk profile from a hosted API. Model behaviour is harder to audit than model code: a fine-tune can carry biases or failure modes that no licence inspection would reveal.

NIST has previously [found](https://www.nist.gov/news-events/news/2025/09/caisi-evaluation-deepseek-ai-models-finds-shortcomings-and-risks) security vulnerabilities in DeepSeek’s open models, and for regulated industries, questions about training data provenance and content handling are live regardless of where a model was built.

The counterargument is about proportionality rather than dismissal. Georgetown research fellow Sam Bresnick has argued that halting Nvidia H200 sales to China would slow Beijing considerably more than banning open models Americans want to use, targeting the input rather than the output. And Ball himself conceded a version of this in his second observation, attributing China’s open-weight strategy partly to a lack of domestic compute for serving customers, which would make it an unintended byproduct of US export controls in the first place.

### What is actually likely to happen.

*[Axios](https://www.axios.com/2026/07/20/ai-us-china-open-source-kimi)* reported on July 20, citing people close to the administration, that Commerce last year weighed adding Chinese AI labs to the Entity List, that the NSA and the Office of the National Cyber Director considered issuing an advisory on Chinese AI lab threats, and that the White House considered an executive order making US companies liable for breaches if they used Chinese models. Officials concerned about stifling innovation killed all of it.

With adviser Sriram Krishnan gone and security hawks louder, the effort has revived, but the described approach is procurement rules, Entity List threats and public pressure rather than prohibition. “What’s actually happening is slower and more durable,” one source told *Axios*. Neither the White House nor Commerce responded to *Axios’s* requests for comment, and *Politico* reports Commerce will not move imminently.

For buyers outside the US, the exposure is indirect but real. A rule written for American regulated industries and federal procurement does not bind a Malaysian bank or an Indonesian telco. The hyperscalers are the transmission line.

Most enterprises in this region reach Kimi K3 through Azure, AWS or Google Cloud rather than Moonshot’s own API, and if Washington makes hosting Chinese open-weight models uncomfortable enough for those providers, the model quietly leaves the catalogue in Kuala Lumpur at the same time it leaves it in Virginia.

Ball anticipated this in his own post, noting that regulators would not want to push so hard that hyperscalers stop serving Chinese models altogether, since that would only drive startups toward less reputable providers. The obvious hedge is to hold your own copy. Moonshot publishes K3’s weights on July 27, and from that point the model cannot be withdrawn from anyone who has downloaded it.

But as covered previously, K3 is a difficult model to self-host: Moonshot recommends serving it across 64 or more accelerators, and the weights alone come to roughly 1.4TB. For most companies, the fallback is theoretical.

That leaves a narrower question than the headlines imply. Not whether Chinese open-weight models are safe or permitted, but whether the specific model you build on will still be in your cloud provider’s catalogue in twelve months, and what it would cost you to move if it isn’t. That is a due-diligence question, and it is answerable today.

**See more: [Kimi K3 open-weight model: China’s biggest AI is a bet on memory, not compute](https://www.artificialintelligence-news.com/news/kimi-k3-open-weight-model-memory-compute-china/)**

![Banner for the AI & Big Data Expo event series.](https://www.artificialintelligence-news.com/wp-content/uploads/2025/08/ai-expo-banner-2025.png)

Banner for the AI & Big Data Expo event series.

**Want to learn more about AI and big data from industry leaders?** Check out [AI & Big Data Expo](https://www.ai-expo.net/?utm_source=AI-News&utm_medium=Footer-banner&utm_campaign=world-series) taking place in Amsterdam, California, and London. The comprehensive event is part of [TechEx](https://techexevent.com/?utm_source=AI-News&utm_medium=Footer-banner&utm_campaign=world-series) and is co-located with other leading technology events including the [Cyber Security & Cloud Expo](https://cybersecuritycloudexpo.com/?utm_source=CloudTech-News&utm_medium=Footer-banner&utm_campaign=world-series). Click [here](https://techexevent.com/?utm_source=AI-News&utm_medium=Footer-banner&utm_campaign=world-series) for more information.

AI News is powered by [TechForge Media](https://techforge.pub/?utm_source=AI-News&utm_medium=Footer-banner&utm_campaign=world-series). Explore other upcoming enterprise technology events and webinars [here](https://techforge.pub/events/?utm_source=AI-News&utm_medium=Footer-banner&utm_campaign=world-series).

[![](https://www.artificialintelligence-news.com/wp-content/uploads/2025/01/TF-Intro-1.webp)](https://bit.ly/45SW1vR)

<iframe frameborder="0" allow="attribution-reporting; run-ad-auction" src="https://googleads.g.doubleclick.net/pagead/ads?client=ca-pub-6116732093001117&amp;output=html&amp;adk=1812271804&amp;adf=3025194257&amp;abgtt=6&amp;lmt=1784746019&amp;plat=3%3A16%2C4%3A16%2C9%3A32776%2C16%3A8388608%2C17%3A32%2C24%3A32%2C25%3A32%2C30%3A1081344%2C32%3A32%2C41%3A32%2C42%3A32%2C43%3A32%2C44%3A32&amp;format=0x0&amp;url=https%3A%2F%2Fwww.artificialintelligence-news.com%2Fnews%2Fchinese-open-weight-models-policy-risk%2F&amp;pra=5&amp;aiof=10&amp;asro=0&amp;aimartd=4&amp;aieuf=1&amp;aicrs=1&amp;uach=WyJXaW5kb3dzIiwiMTkuMC4wIiwieDg2IiwiIiwiMTUwLjAuNzg3MS4xMjkiLG51bGwsMCxudWxsLCI2NCIsW1siTm90O0E9QnJhbmQiLCI4LjAuMC4wIl0sWyJDaHJvbWl1bSIsIjE1MC4wLjc4NzEuMTI5Il0sWyJHb29nbGUgQ2hyb21lIiwiMTUwLjAuNzg3MS4xMjkiXV0sMF0.&amp;dt=1784746019306&amp;bpp=3&amp;bdt=498&amp;idt=78&amp;shv=r20260721&amp;mjsv=m202607200101&amp;ptt=9&amp;saldr=aa&amp;abxe=1&amp;cookie_enabled=1&amp;eoidce=1&amp;nras=1&amp;correlator=3943270202818&amp;frm=20&amp;pv=2&amp;u_tz=330&amp;u_his=6&amp;u_h=1067&amp;u_w=1707&amp;u_ah=1067&amp;u_aw=1707&amp;u_cd=24&amp;u_sd=1.5&amp;dmc=16&amp;adx=-12245933&amp;ady=-12245933&amp;biw=1692&amp;bih=945&amp;scr_x=0&amp;scr_y=0&amp;eid=95395795%2C95396139%2C31099838&amp;oid=2&amp;pvsid=8922355908396105&amp;tmod=1226476435&amp;uas=1&amp;nvt=6&amp;fsapi=1&amp;ref=https%3A%2F%2Fwww.artificialintelligence-news.com%2F&amp;fc=1920&amp;brdim=0%2C0%2C0%2C0%2C1707%2C0%2C1707%2C1067%2C1707%2C945&amp;vis=1&amp;rsz=%7C%7Cs%7C&amp;abl=NS&amp;fu=32768&amp;bc=31&amp;bz=1&amp;pgls=CAEaBTcuMC4y~CAEQBRoFNC4yLjA.&amp;ifi=1&amp;uci=a!1&amp;fsb=1&amp;dtd=132" title="Advertisement" aria-label="Advertisement"></iframe>