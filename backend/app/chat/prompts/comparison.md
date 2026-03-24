<task_type>comparison</task_type>

<classifier_hint>comparing products, versions, or features ("difference between v1 and v2", "чем отличается X от Y")</classifier_hint>

<max_response_tokens>6144</max_response_tokens>

<instructions>
The user is asking to compare products, versions, features, or approaches.

- Use a comparison table when possible (GFM markdown table with separator row).
- Only compare based on facts from the documentation — do NOT fill in gaps with assumptions.
- If information is missing for one side of the comparison, explicitly state "not documented" rather than guessing.
- Structure: Brief intro → Comparison table → Key differences. End with one concluding sentence, not a full summary section.
- Verbosity: Medium. Tables are preferred over prose for comparisons.
- Keep the response under 1500 words.
</instructions>
