\[Update: I made a [video walking through this article](https://youtu.be/WKKC5Xvt3pc) that you can use to supplement the reading!\]

I’m writing this piece in an attempt to clear the perennial confusion that sits heavily atop everybody’s favourite algorithmic concept — *dynamic programming*. Having grappled with it aggressively for a good 4 months or so, I’ve seen first-hand how much of a monster it can be with respect to both understanding and implementation. What I’d like to offer here is a foundational explanation on approaching dynamic programming in a way that builds from the ground-up, and is both comprehensive and exhaustive — something I haven’t found anywhere myself.

For what it’s worth, if you don’t put the hours in it will still be incredibly difficult to grasp. However, I hope that a fresh perspective will help shine light on every dimension of dynamic programming (DP).

Finally, my aim is also to break DP down into well defined problem-solving steps in such a way that you can both regurgitate and implement them yourselves when you’re facing a DP-style problem in your tech interviews. If you can explain your logic from the ground-up (as we will in this article), I pinky promise that you will get a big, fat checkmark from your interviewers who will appreciate the depth from which you built up your answer.

![](https://miro.medium.com/v2/resize:fit:1400/format:webp/0*8eTm7Dd28FhM3F-5.png)

A valueless photo that I’m including because Medium won’t let me manually set a thumbnail.

**Prerequisites**

- **Patience**. This article will be a bit long, and it will be a bit dense. I understand that hard writing makes for easy reading, so I’ve done my best to make this article as understandable as possible. However, this isn’t one that you can fly through.
- **Recursion**.I strongly suggest you have a firm understanding of recursion. At the time of this writing, I haven’t written anything about recursion, and I’m not sure that I plan to. Unlike for DP, I feel there are plenty of sufficient resources out there that can be found with a quick search. Many of them do a mighty fine job of covering the topic.

**Perspective**

Before diving into the definitions and the nitty-gritty of DP, I would like to begin by taking a step back and sharing what I feel is the most appropriate way to look at the concept of DP. I would summarize it in the following way:

==*Dynamic Programming is a*== ==tool== ==*that will help make your recursive code more efficient.*==

I’d really like to drill home the fact that I don’t think we should consider any given problem a “DP problem” right off the bat. More appropriately, I’d argue that we should always begin by identifying that we have a problem in front of us that requires the use of *recursion*.

From there (and we will dive deeper into this later) we will be in a position to acknowledge that there may be some redundancy in the recursive calculations we are doing, and that perhaps there is a way through which we can improve upon our solution.

That *method of improvement* is dynamic programming.

I think it is counterproductive to look at a brand new problem and try to jump to the conclusion of whether or not it is a DP problem; it’s an inefficient use of the horsepower between your ears, it doesn’t bode well for explaining your thought process in an interview, and it’s a bit intellectually dishonest.

So, to reiterate, we use dynamic programming as a *tool* for *improving a pre-existing solution*!

Most people fail to notice this (I definitely did) and this is often the case because of how solutions to everyone’s favourite “DP problems” are presented. Say for instance we jump online to find a solution to the Coin Change problem or the 0–1 Knapsack problem. More often than not, the websites we visit or the YouTube videos we watch begin by either:

*1) noting that what we’re facing is a dynamic programming problem, and/or*

*2) stating that we will use dynamic programming to solve this problem.*

**But there is a fundamentally implicit step that occurs before we reach either of these conclusions!**

And if we can pause to acknowledge what this initial step is, then we will, by extension, gain the foundational understanding of what drives the necessity of this problem-solving tool.

This initial step will most often be succeeded by 3 more steps, totalling a 4-pronged approach in understanding and tackling DP. The rest of the article will dive into each of these steps, and how to make sense of them from start to finish.

For the purpose of a consistent explanation, I’ve decided to use one problem for each of the four steps, with each successive step displaying an incremental improvement over its predecessor.

**The Problem**

The problem will be [Leetcode #62 — Unique Paths](https://leetcode.com/problems/unique-paths/), which states the following:

A robot is located at the top-left corner of an *m* x *n* grid. The robot can only move either down or right at any point in time. The robot is trying to reach the bottom-right corner of the grid. How many possible unique paths are there?

![](https://miro.medium.com/v2/resize:fit:1100/format:webp/0*zvQede7--TNKtpUO.png)

A diagram provided by the Leetcode link above depicting an example of a 3x7 board.

(The purpose of this article is to shed light on the DP thought process, not to get buried in the details of the problem itself. As such, I won’t be diving too deeply into problem-specific points, beyond what is absolutely necessary. If you’d like to get an in-depth solution to this problem — and *many* others — check out my data structures & algorithms [YouTube channel](https://www.youtube.com/channel/UCC3khuMWGcaxs6dl9db5Yrg?view_as=subscriber) for a whole boatload of tutorials.)

**Step 1: Recursion**

The initial step that I mentioned above will always (*always*) be to **begin by outlining what your pure, raw, unadulterated recursive solution will look like**.

No dynamic programming, no memoization, and no other fancy 10+ letter terminology.

I’d argue that this is the hardest part of solving most problems, especially ones that eventually require the use of dynamic programming for further optimization. It’s during this step that we need to lay out our attack plan by identifying what the essence of the problem requires.

(I know that sounds vague, but for an article addressing general problem solving, it kind of has to be. Each problem is unique, and the more of them you do, the better you’ll get at learning how to tackle them with style and grace.)

This step is *de facto* the equivalent to coming up with the brute force solution. You need to convince yourself, and your interviewer, that you understand the *recursive relationship* required to solve this problem.

In the Unique Paths problem, the recursive relationship (which may not be obvious at first) is to understand that the number of unique paths from any given step (*m,* *n)* is the sum of the number of unique paths from (*m-1, n)* and (*m, n-1)*.

That is, for the robot to get to the end from its current position, its number of paths depends on the number of paths to the end if it were to take a step right *plus* the number of paths to the end if it were to take a step down.

Let’s take a look at the code snippet below which contains a simple helper function with a terminal condition (line 8) and a 1-line recursive relationship (line 11).

The terminal condition is that `m == 1 or n == 1 `. Logically, this is the case because *m == 1* and *n == 1* imply that we are standing either on the bottom row, or the rightmost column. At either of these positions, there is only 1 way to make it to the end (i.e. keep walking right, or keep walking down, respectively.)

The recursive relationship is rather self explanatory, and is a direct code implementation of the approach discussed above.

\[Note that within the context of `helper` function below, `m` and `n` referred to in the previous paragraph refer to how many steps we are away from leaving the grid. A value of 1 for either variable implies we’ve taken as many steps down / right as we possibly can, while staying in the boundaries. If this seems a bit unintuitive, don’t fret — we’ll clean this all up shortly below.\]

Although our solution so far is inefficient, the key takeaway is that we have determined the recursive relationship in understanding how to get the number of unique paths to the end from any given cell by referring appropriately to its neighbouring cells.

This is *exactly* where you want to be at the end of the first step of your solution.

(With my tail between my legs, I’ll admit that I struggled to get the exact time complexity of the brute force solution. However, if you were to draw the recursive calls out by hand they would look similar to the [recursive Fibonacci solution](https://i.stack.imgur.com/QVSdv.png) where we end up recalculating the same Fibonacci values multiple times over, leaving us with an exponential time solution. This is what leads me to estimate the exponential time complexity in this similar case — that’s about as much as you’d need to identify in an interview.)

**Step 2: Recursion + Memoization**

Now we need to figure out how to take our previously inefficient solution and turn it into something more digestible. Step 2 is where we actually begin using dynamic programming. However, before jumping head first into that, we need to specifically define the conditions under which we can actually start to consider whether a problem warrants the use of dynamic programming.

DP can and should be used if, by nature of your Step 1 solution, there are:

*1) overlapping subproblems, and*

*2) an optimal substructure*

Or, in plain English:

*1) you’re solving the same subproblem multiple times over, and*

## Get Aleks’s stories in your inbox

Join Medium for free to get updates from this writer.

*2) by finding the optimal solution to a subproblem, you’re able to extract an optimal solution to the entire problem more-or-less for free*

That’s it. And when you’re interviewing, you should *definitely* state these two conditions loud and clear. If they are both met, we can go ahead and proceed with the rest of information in the article below. If they are not, the problem wouldn’t classify as being solvable using DP. There may or may not be other optimizations, but they wouldn’t be solved using any of the DP techniques below, so you can go ahead and count your blessings (only half joking.) For those of you that aren’t so fortunate, keep on reading!:)

\[If it’s not entirely obvious that this problem has overlapping subproblems, try to recreate the call pattern for this problem in a similar way to the Fibonacci problem [linked above](https://i.stack.imgur.com/QVSdv.png). The second condition is met by virtue of the fact that we can solve the number of paths at (*m, n*) using (*m-1, n*) and (*m, n-1*).\]

If the above two conditions are met, we need to act on them. If we’re solving the same subproblem multiple times over, let’s find a way to *not* do that. That is, let’s find a way to solve it once and remember the solution to it by storing it away somewhere for safe keeping.

This process is what’s referred to as *memoization*.

More often than not, we do this by storing the result in a data structure that will allow us to look the result up in the future in O(1) time (e.g. an array, a hash table / dictionary, a set, etc.)

The good news is that typically to go from Step 1 to Step 2 requires *very little* incremental code. Apart from initializing a data structure to house the results, we’ll only need to add two items:

*1) One line of code to store the result of a recursive call once we’ve calculated it*

*2) One piece of logic to check whether an item has already been calculated; if it has been, we will retrieve it and use it as opposed to recalculating it*

In the code snippet below, you can find these on lines 7 and 10, respectively.

On line 7, we initialized an array called `dp` to a size of *m+1* x *n + 1*, which almost replicates the *m* x *n* grid given in the problem description. In this particular step, I chose dimensions of *m+1* x *n + 1* in order to avoid getting an out of bounds error when using *m* and *n* as indices for checking `dp`. You would be equally as justified in creating an array of size *m* x *n*, and then returning `helper(m-1, n-1)`, and making appropriate index corrections in the `helper` function as well — to each their own:)

On line 10, we added a terminal condition checking that if a given entry at `dp[m][n] != 0` then we want to return that value as we have previously calculated it!

You may also notice that the terminal condition from Step 1 still exists on line 12; however, we’ve now taken the time to actually update `dp` with the total number of paths from the given cell we’re on — which will be 1, because we would be sitting at either the bottom row or rightmost column as noted in Step 1.

Finally, if we make it to line 16 without hitting either terminal condition, we will update the entry at `dp[m][n]` accordingly with the recursive relationship we established in Step 1. At this point, however, if we’ve already calculated the number of unique paths from a cell that’s to the right of or below us, we will immediately get that stored value from the terminal condition upon function call.

**Now, the next time this particular combination of** `**m**` **and** `**n**` **is called, we’re ready for it — *no more repeated calculations!***

At this point you may notice that we’ve introduced additional space complexity to our solution, and you’d be right! We need to acknowledge (both internally, and to our interviewer) that we may need to sacrifice some space in order to improve time. In many problems that lead to a DP solution, this trade-off will be a no-brainer because it will often only increase space complexity linearly or by a constant factor, but will exponentially improve time complexity. Again, though, it’s something you should actively acknowledge before implementing it.

One more piece of good news: if you’ve made it this far in your interview, you’re looking pretty damn decent right about now. There may likely exist further optimizations (discussed below) but if you’ve comprehensively explained the logic behind the problem, implemented the brute force solution, and then improved on it using memoization after noting that your solution fits eligibility criteria for dynamic programming, then you’re well on your way onto the next round. (Of course, I can’t make an absolutist statement in this regard because every interviewer is different, and so are different companies’ expectations. However, you’ve done a lot of the heavy lifting at this point, and you’re looking real solid. Keep reading below to see how we can keep moving along!)

**Step 3: Iteration + Tabulation**

Step 3 is *almost* always a viable next option. Key word *almost*. If you don’t see a way of improving upon your previous step using the information in this section, and/or your interviewer is more than glad with how you’ve set up your recursion and memoization, you can call it a day and move onto whatever’s next to tackle on your list. Otherwise, buckle up because we’re shifting gears once again.

This third step involves solving the problem using iteration instead of recursion.

We will also use *tabulation* instead of *memoization*. Fundamentally, both accomplish the same goal — they store calculations we’ve previously done in order to reuse them for future iterations. However, *tabulation* will involve storing calculations in an array (most often a 2-dimensional one), while *memoization* most commonly refers to storing calculations in a set, object, dictionary, etc. *Tabulation* is what will allow us to iteratively walk through an array without relying on recursive calls.

Note that these two changes *may* *not* necessarily bring upon any improvements with respect to asymptotic analysis (i.e. time and space complexities). However, the benefit to modifying to an iterative solution lays in the fact that your program will be able to run larger inputs as it is *no longer limited to the maximum size of the call stack*.

We often forget to note the limitation of call stack size; that is, the call stack does actually have a maximum size that it can reach before it overflows. For example, if you’re coding in Python, this maximum is 997 calls (the maximum stack size is relatively low in Python because the stack frames themselves tend to be quite thick.) So just because switching to iteration will not necessarily fix your Big O time and space complexities, it could allow you to break free of the bottleneck imposed by maximum call stack size (as well as to set you up for potential space complexity improvement in Step 4.)

When you visit YouTube and watch a video of somebody filling out an *m* x *n* table one value at a time, they’ve basically jumped to Step 3. And some of those videos are class; top drawer stuff that really does provide a quality solution. However, many of them fail to sequentially walk through the logic on *how they got to that solution*.

This is the main reason why I wanted to write this article.

Most often, these teachers have only *implicitly* realized what the brute force recursive solution would be, including what the recursive relationship is. They have also concluded that there is a clear case of overlapping subproblems and an optimal substructure (i.e. Step 1.) If you’re lucky, they did the latter out loud.

They have then most likely identified that the solution could be cleaned up using some simple memoization, usually in the form of storing calculations in an array / hash table / dictionary / set (i.e. Step 2.)

Typically, it’s only *after* all this has been done that it’s appropriate to jump in and identify that it can be done iteratively in a way that will help us eliminate the call stack size constraint, and potentially even set us up for optimizing space complexity in the next step.

My personal qualm with many of these resources that jump straight into Step 3 deceptively (albeit unknowingly) don’t take the time to explain how or why they got there. And quite often we end up looking like chimps as we‘re sat staring at code with Victorian-era elegance, wondering how on God’s green earth we’d come up with this in an interview setting.

The secret to getting there, once again, lays precisely in Steps 1 and 2.

Now, let’s put some context around this point now with another look at Unique Paths. (For a more comprehensive walkthrough of this solution, you can checkout my YouTube video of it [here](https://www.youtube.com/watch?v=vzzJpyDyE3g).)

We’ve made a slight adjustment to our `dp` table here which I think reads more intuitively for this solution. In particular, we’ve gone ahead and made it of size *m* x *n*, with all initial values set to 1.

In lines 9–11, we walk through this table *backwards* from the cell in the second last row and second last column. (This may not be naturally intuitive, but it is a great trick to consider when filling out a table in problems similar to this one; I use this quite often for problems that require figuring out just about anything regarding getting from point *A* to point *B*.)

Notice that every cell in the bottom row and rightmost column will both be filled with 1 and only 1. As noted in Step 1, the reason for this is because from any one of those cells there is exactly 1 way to get to the end. By walking backwards, this allows us to access the number of paths from the cells to our right and below in constant time. It’s an incredibly clean way of filling the table that ends with our entry `dp[0][0]` representing the number of unique paths from the start of the grid.

Once more, notice that the time and space complexities are identical in Steps 2 and 3. However, we’re finally free of that pesky maximum call stack size — and boy does freedom ever taste good.

And just to score some extra brownie points, I’d like to think that this code looks far sexier than what we’ve previously done. It’s tidy, compact, and quite succinct as well.

**Step 4: Iteration + Tabulation \[Optimized\]**

As with the previous step, this one is quite often viable, though strictly speaking this is *not* always true. (I will also add that if you’ve gotten soundly through the first 3 steps in an interview, you’re very much sitting pretty, and this would be the icing on the cake. Don’t lose any sleep over the fact that you may not get here every time).

With that said, let’s see what we can do about improving our previous solution. Specifically, there may exist an opportunity to trim down on that *space* complexity (at this point, the time complexity is as optimal as it’s ever going to get.)

In many instances where we create an iterative DP solution using tabulation of grid size *m* x *n*, we don’t actually need constant access to the entire table at one time. This point is definitely true for Unique Paths.

If you think about the recursive relationship we established, we can see that the only row we ever need reference to is the row that is directly *below* our current cell, and the one cell immediately to our right.

If we find a way to capitalize on this fact, that would mean that we don’t actually need a full *m* rows to be stored anymore; rather (in this case) 2 would be sufficient, which would definitely improve our space complexity. Let’s have a look at how we can do that in the snippet below.

With merely two small changes from Step 3, we’ve improved our space complexity by a factor of *m*. The changes are on lines 7 and 12.

On line 7, we now only create a table with 2 rows, as opposed to our previous *m* rows. Simple enough.

On line 12, we set our bottom row to equal our top row. The reason we do this is because, as you can see on line 11, we will simply be filling in the top of the two rows in our `dp` table. To fill in the top row, we will be accessing the bottom row. Once this top row is filled, we’ll need to access it for our next set of calculations, which is why we do the equivalent of moving it one step down and making way another round of additions. (Once again, note that we start from the second-rightmost column; the rightmost column will always keep a value of 1.)

After all that, our solution is finally completed!

Like with all fine things in life, with enough practice these will start to become second nature. If you’re feeling slightly overwhelmed or discouraged, I’d suggest taking a breather, going through this article bit-by-bit once again, and trying to apply the steps yourself on various DP-labelled problems on Leetcode. The first few may be rough, but you’ll get the hang of it.

*Whew*! If you’ve made it this far, congratulations. This was a heavy one — we learned about how to think about DP, under what conditions it can be implemented, and the 4 steps we use to go from zero-to-hero on any recursive problem that fits the DP criteria.

I hope that all the points above were sensible, informative, and opened up an opportunity for you to have a deeper understanding of the essence of dynamic programming, and what drives its necessity. As always, I’m more than happy to take any questions, comments, or feedback down below:) Happy coding!