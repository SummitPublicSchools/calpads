"""Abstract the form parser
The form parser needed to house more information than would be
helpful to expose to the users of the API.

This abstraction has two goals:
1) Store all of the information needed to fulfill the API request
2) Produce a way to expose exactly what a user would need, not too much
"""
import logging
import unicodedata
from lxml import etree

REPORTS_DL_FORMAT = {'CSV': 'CSV',
                     'WORD': 'WORDOPENXML',
                     'EXCEL': 'EXCELOPENXML',
                     'POWERPOINT': 'PPTX',
                     'PDF': 'PDF',
                     'TIFF': 'IMAGE',
                     'MHTML': 'MHTML',
                     'XML': 'XML',
                     'DATAFEED': 'ATOM'}

class ReportsForm:

    def __init__(self, page_source):
        """Page source is the HTML string in which the Reports form can be found
        This is usually from the `response.text`.
        """
        self.page_source = page_source
        self.root = etree.fromstring(page_source, parser=etree.HTMLParser(encoding='utf8'))
        self.log = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        stream_hdlr = logging.StreamHandler()
        stream_hdlr.setFormatter(logging.Formatter(fmt=log_fmt))
        self.log.addHandler(stream_hdlr)
        self.complete_parse = self.parse_the_form()
        #self.log.debug(self.complete_parse)
        self.filtered_parse = self.filter_parsed_form()

    def parse_the_form(self):
        all_form_elements = self.root.xpath("//*[@data-parametername]")
        params_dict = dict.fromkeys([tag.attrib['data-parametername'] for tag in all_form_elements])
        #self.log.debug('This is the init params_dict: \n{}'.format(params_dict))
        for element in all_form_elements:
            tag_combos = []
            key = element.attrib['data-parametername']
            for child in element.xpath('.//*'):
                tag_combos.append(
                    child.tag)  # Find all the tags that are under the parameter div (i.e. where the form field is located)
                if 'calendar' in child.attrib.get('class', ''):
                    tag_combos = tag_combos[
                                 :-2]  # If it's a calendar date input, remove the last two tags so it's treated like a textbox
            params_dict[key] = [tuple(tag_combos)]

        for parametername, param_values in params_dict.items():
            if param_values[0][0] == 'select':
                select = self.root.xpath("//*[@data-parametername='{}']//select".format(parametername))[0]
                param_values.append(('select',
                                     tuple((unicodedata.normalize('NFKC', option.text),
                                            # This is the key associated with the request form data
                                            select.attrib.get('name'),
                                            # The value is what actually needs to be passed to the form upon submission
                                            unicodedata.normalize('NFKC', option.attrib.get('value')))
                                           for option in select.xpath('.//*')
                                           if unicodedata.normalize('NFKC', option.text) != '<Select a Value>')
                                     )
                                    )

            elif param_values[0][-1] == 'input':
                param_values.append(('textbox', ('plain text',
                                                 self.root.xpath("//*[@data-parametername='{}']"
                                                            .format(parametername))[0]
                                                 .xpath(".//input")[0]
                                                 .get('name'))
                                     ))

            elif param_values[0][-1] == 'label':
                param_values.append(('textbox_defaultnull', ('plain text',
                                                             '') # TODO: Test out how to get the name value for this case
                                     ))

            else:
                form_input_div = self.root.xpath("//*[@data-parametername='{}']".format(parametername))[0]
                div_id = form_input_div.attrib['id'] + '_divDropDown'
                all_input_labels = self.root.xpath('//*[contains(@for, "{}")]'.format(div_id))
                all_input_labels_txt = [unicodedata.normalize('NFKC', label.text) for label in all_input_labels
                                        if unicodedata.normalize('NFKC', label.text) != '(Select All)']
                dict_opts = dict.fromkeys(all_input_labels_txt)
                for idx, item in enumerate(all_input_labels_txt):
                    dict_opts[item] = ((True, False),
                                       self.root.xpath('//input[@type="hidden" and contains(@id, "{}")]'
                                                  .format(div_id))[0].attrib.get('name'),
                                       str(idx)
                                       )  # Append the index which will be used for filling in the form
                param_values.append(('dropdown', dict_opts))

        return params_dict

    def filter_parsed_form(self):
        filtered_dict = dict()
        for paramname, param_values in self.complete_parse.items():
            if param_values[1][0] == 'select':
                filtered_dict[paramname] = tuple(options[0] for options in param_values[1][1])
            elif param_values[1][0] == 'dropdown':
                filtered_dict[paramname] = dict.fromkeys(param_values[1][1].keys(), (True, False))
            elif param_values[1][0] in ('textbox', 'textbox_defaultnull'):
                filtered_dict[paramname] = ("You can insert any string here",)

        return filtered_dict

    def get_default_form_data(self):
        """The default form data comes with all "dropdown" fields pre-filled, but requires inputs for other fields"""
        all_with_names = self.root.xpath('//*[@name]')
        # self.log.debug(all_with_names)
        form_inputs_to_keep = ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']
        form_inputs_endings = ('HiddenIndices', 'txtValue', 'ddValue')

        in_expected_keys = [tag for tag in all_with_names if tag.attrib['name'] in form_inputs_to_keep
                            or tag.attrib['name'].endswith(form_inputs_endings)]
        in_expected_keys_names = [tag.attrib['name'] for tag in in_expected_keys]
        values_in_expected_key_tags = [tag.attrib.get('value', '') for tag in in_expected_keys]
        return dict(zip(in_expected_keys_names, values_in_expected_key_tags))

    def fill_form(self, form_data):
        to_submit = dict()
        for paramname, paramvalue in form_data.items():
            #Check if the key that the user provided is expected, otherwise log and do nothing
            if self.complete_parse.get(paramname):
                if self.complete_parse[paramname][1][0] == 'select':
                    #self.log.debug(self.complete_parse[paramname][1][1])
                    formname = self.complete_parse[paramname][1][1][0][1] #TODO: Make value easier to get?
                    formval = None
                    for val_tuple in self.complete_parse[paramname][1][1]:
                        if val_tuple[0].lower() == paramvalue.lower():
                            formval = val_tuple[2]
                    if formval is None:
                        self.log.info("Provided {} input was not processed: {}"
                                      .format(paramname, paramvalue))
                        continue
                    to_submit[formname] = formval
                elif self.complete_parse[paramname][1][0] == 'dropdown':
                    valid_dict = self.complete_parse[paramname][1][1]
                    formname = valid_dict[list(valid_dict.keys())[0]][1] #TODO: Maybe we should make this value easier to get?
                    formval = ''
                    for checkbox, checked in paramvalue.items():
                        if checkbox in valid_dict.keys():
                            if checked: #Double checking that the user sent True/truthy value
                                if formval:
                                    formval = ','.join([formval, valid_dict[checkbox][2]])
                                else:
                                    formval += valid_dict[checkbox][2]
                    if formval == '':
                        self.log.info("Provided {} input was not processed: {}"
                                      .format(paramname, paramvalue))
                        continue
                    to_submit[formname] = formval
                elif self.complete_parse[paramname][1][0] in ('textbox', 'textbox_defaultnull'): #TODO: defaultnull still needs testing
                    formname = self.complete_parse[paramname][1][1][1]
                    to_submit[formname] = paramvalue
            else:
                self.log.info("Provided input was not processed: {}".format(paramname))
        return to_submit

    def get_final_form_data(self, form_data):
        # Update the default form data with what the user has provided
        final_form = self.get_default_form_data()
        final_form.update(self.fill_form(form_data))
        return final_form
