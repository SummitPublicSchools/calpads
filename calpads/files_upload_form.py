"""Extract form handler"""
import logging

class FilesUploadForm:

    def __init__(self, form_root):
        """Takes in the root form node returned by lxml.etree.fromstring()"""
        self.root = form_root
        self.named_fields = [tag for tag in self.root.xpath('.//*[@name]')]
        self.prefilled_fields = [(field.attrib['name'], field.attrib.get('value'))
                                 for field in self.named_fields]
        self.log = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        stream_hdlr = logging.StreamHandler()
        stream_hdlr.setFormatter(logging.Formatter(fmt=log_fmt))
        self.log.addHandler(stream_hdlr)

    def get_parsed_form_fields(self):
        all_parsed_options = dict()
        all_parsed_options.update(self.find_text_inputs())
        all_parsed_options.update(self.find_selects())

        return all_parsed_options

    def find_text_inputs(self):
        text_inputs = [tag for tag in self.named_fields
                      if tag.tag == 'input'
                      and tag.attrib.get('type') == 'text']
        text_options = [(tag.attrib['name'],
                             {'Required': False,
                              'ValidValues': str})
                            for tag in text_inputs]
        return dict(text_options)

    def find_selects(self):
        selects = [tag for tag in self.named_fields
                           if tag.tag == 'select']
        return self._scrape_options_to_dict(selects, False)

    def _scrape_options_to_dict(self, selects, allow_multiple=True):
        options_dict = dict()
        for tag in selects:
            options = [(option.text, option.attrib.get('value'))
                       for option in tag.xpath('.//option')]
            options_dict[tag.attrib['name']] = {'Required': True,
                                                'ValidValues': dict([('_allows_multiple', allow_multiple)] + options)}

        return options_dict