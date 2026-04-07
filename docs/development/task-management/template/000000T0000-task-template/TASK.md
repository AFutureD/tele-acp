# Task Name


<!--
Meta JSON Schema

{
  "$schema": "https://json-schema.org/draft-07/schema",
  "type": "object",
  "properties": {
    "Task": {
      "type": "string",
      "description": "ID-SLUG"
    },
    "Author": {
      "type": "string",
      "description": "The author of this task"
    },
    "Status": {
      "type": "string",
      "description": "The current status of this task",
      "enum": [
        "DRAFT",
        "DONE",
        "DEVELOPING"
      ]
    },
    "Type": {
      "type": "string",
      "description": "The type of this task",
      "enum": [
        "FEAT",
        "BUG"
      ]
    },
    "Related": {
      "type": "array",
      "description": "Related tasks",
      "uniqueItems": true,
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "Task",
    "Author",
    "Status",
    "Type"
  ]
}

-->

* Task: 000000T0000-task-template
* Author: [Author 1](https://github.com/example)
* Status: DRAFT
* Type: FEAT
* Related: [000000T0000-task-template](../000000T0000-task-template)

## Content

Use this file to describe the task clearly and concisely.

The content can follow these guidelines:
1. Reference related file paths when helpful.
   - `[example-snapshot.png](./assets/example-snapshot.png)`
   - `[related-task](../000000T0000-task-template)`
2. Include references and footnotes whenever they add useful context.

## Acknowledgments

If significant changes or improvements suggested by members of the 
community were incorporated into the proposal as it developed, take a
moment here to thank them for their contributions. Swift evolution is a 
collaborative process, and everyone's input should receive recognition!

Generally, you should not acknowledge anyone who is listed as a
co-author or as the review manager.

## References

- [Swift Evolution Template](https://github.com/swiftlang/swift-evolution/blob/main/proposal-templates/0000-swift-template.md)
