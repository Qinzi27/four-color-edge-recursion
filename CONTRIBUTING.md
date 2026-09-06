# Contributing / 如何参与核验

The most useful contribution is a specific, reproducible mathematical observation.
Please state the proposition or code path you are checking, the graph and its
embedding, the input labels, the expected behavior, and the observed result.

欢迎提交文献补充、证明中的具体问题和小型反例。请区分：

- 对数学命题的反例；
- 对当前贪心选择或受限规则的反例；
- 程序错误或输入超出范围；
- 对原创性判断有影响的已有文献。

A failed greedy extension does not establish that a plane map needs five colors.
Finite successful experiments do not establish a theorem for every plane map.
A conflict witness is not claimed to be minimum unless minimality is proved.

Run before proposing code changes:

```sh
python -m unittest discover -s tests -v
python scripts/validate.py
```

Keep the core standard-library-only and add comments explaining mathematical
conventions. Include a genuinely independent check when changing a recurrence.
Please discuss substantial code submissions with the maintainer while the
repository's reuse license remains undecided.
