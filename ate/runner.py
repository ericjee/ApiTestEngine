import copy
import requests

from ate import exception, response
from ate.context import Context
from ate.testcase import parse_template


class TestRunner(object):

    def __init__(self):
        self.client = requests.Session()
        self.context = Context()
        self.testset_req_overall_configs = {}

    def update_context(self, config_dict, level="testcase"):
        """ create/update context variables binds
        @param (dict) config_dict
            {
                "name": "description content",
                "requires": ["random", "hashlib"],
                "function_binds": {
                    "gen_random_string": \
                        "lambda str_len: ''.join(random.choice(string.ascii_letters + \
                        string.digits) for _ in range(str_len))",
                    "gen_md5": \
                        "lambda *str_args: hashlib.md5(''.join(str_args).\
                        encode('utf-8')).hexdigest()"
                },
                "variable_binds": [
                    {"TOKEN": "debugtalk"},
                    {"random": {"func": "gen_random_string", "args": [5]}},
                ]
            }
        @param (str) context level, testcase or testset
            only when level is testset, shall we update testset_req_overall_configs
        """
        requires = config_dict.get('requires', [])
        self.context.import_requires(requires)

        function_binds = config_dict.get('function_binds', {})
        self.context.bind_functions(function_binds)

        variable_binds = config_dict.get('variable_binds', [])
        self.context.bind_variables(variable_binds)

        if level == "testset":
            self.testset_req_overall_configs = config_dict.get('request', {})

    def run_test(self, testcase):
        """ run single testcase.
        @param (dict) testcase
            {
                "name": "testcase description",
                "requires": [],  # optional, override
                "function_binds": {}, # optional, override
                "variable_binds": {}, # optional, override
                "request": {
                    "url": "http://127.0.0.1:5000/api/users/1000",
                    "method": "POST",
                    "headers": {
                        "Content-Type": "application/json",
                        "authorization": "${authorization}",
                        "random": "${random}"
                    },
                    "body": '{"name": "user", "password": "123456"}'
                },
                "extract_binds": {},
                "validators": []
            }
        @return (tuple) test result of single testcase
            (success, diff_content_list)
        """
        self.update_context(testcase)

        # each testcase shall inherit from testset request configs,
        # but can not override testset configs,
        # that's why we use copy.deepcopy here.
        testcase_request = copy.deepcopy(self.testset_req_overall_configs)
        testcase_request.update(testcase["request"])

        parsed_request = parse_template(testcase_request, self.context.variables)
        try:
            url = parsed_request.pop('url')
            method = parsed_request.pop('method')
        except KeyError:
            raise exception.ParamsError("URL or METHOD missed!")

        resp = self.client.request(url=url, method=method, **parsed_request)
        resp_obj = response.ResponseObject(resp)

        extract_binds = testcase.get("extract_binds", {})
        extracted_variables_mapping = resp_obj.extract_response(extract_binds)
        self.context.update_variables(extracted_variables_mapping)

        validators = testcase.get("validators", [])
        diff_content_list = resp_obj.validate(validators, self.context.variables)

        return resp_obj.success, diff_content_list

    def run_testset(self, testset):
        """ run single testset, including one or several testcases.
        @param (dict) testset
            {
                "name": "testset description",
                "config": {
                    "name": "testset description",
                    "requires": [],
                    "function_binds": {},
                    "variable_binds": [],
                    "request": {}
                },
                "testcases": [
                    {
                        "name": "testcase description",
                        "variable_binds": {}, # override
                        "request": {},
                        "extract_binds": {},
                        "validators": {}
                    },
                    testcase12
                ]
            }
        @return (list) test results of testcases
            [
                (success, diff_content),    # testcase1
                (success, diff_content)     # testcase2
            ]
        """
        results = []

        config_dict = testset.get("config", {})
        self.update_context(config_dict)
        testcases = testset.get("testcases", [])
        for testcase in testcases:
            result = self.run_test(testcase)
            results.append(result)

        return results

    def run_testsets(self, testsets):
        """ run testsets, including one or several testsets.
        @param testsets
            [
                testset1,
                testset2,
            ]
        @return (list) test results of testsets
            [
                [   # testset1
                    (success, diff_content),    # testcase11
                    (success, diff_content)     # testcase12
                ],
                [   # testset2
                    (success, diff_content),    # testcase21
                    (success, diff_content)     # testcase22
                ]
            ]
        """
        return [self.run_testset(testset) for testset in testsets]
