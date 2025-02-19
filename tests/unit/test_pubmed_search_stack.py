import aws_cdk as core
import aws_cdk.assertions as assertions

from pubmed_search.pubmed_search_stack import PubmedSearchStack

# example tests. To run these tests, uncomment this file along with the example
# resource in pubmed_search/pubmed_search_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = PubmedSearchStack(app, "pubmed-search")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
