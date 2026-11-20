using System;
using System.Collections.Generic;
using FluentAssertions;
using FluentValidation;
using FluentValidation.Results;
using Moq;
using NUnit.Framework;
using NzbDrone.Core.Indexers;
using NzbDrone.Core.Indexers.Newznab;
using NzbDrone.Core.Localization;
using NzbDrone.Test.Common;
using Prowlarr.Api.V1.Indexers;
using Prowlarr.Http.ClientSchema;

namespace NzbDrone.Api.Test.Indexers
{
    [TestFixture]
    public class IndexerValidationFixture : TestBase<IndexerController>
    {
        private NewznabSettings _settings;

        [SetUp]
        public void Setup()
        {
            _settings = new NewznabSettings { BaseUrl = "https://indexer.example" };
            Mocker.GetMock<ILocalizationService>()
                .Setup(x => x.GetLocalizedString(It.IsAny<string>(), It.IsAny<Dictionary<string, object>>()))
                .Returns<string, Dictionary<string, object>>((key, args) => key);
            SchemaBuilder.Initialize(Mocker.Container);
            Mocker.GetMock<IIndexer>().SetupGet(x => x.Protocol).Returns(DownloadProtocol.Usenet);
            Mocker.GetMock<IIndexer>().SetupGet(x => x.SupportsRedirect).Returns(true);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.GetInstance(It.IsAny<IndexerDefinition>())).Returns(Mocker.GetMock<IIndexer>().Object);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.Test(It.IsAny<IndexerDefinition>())).Returns(new ValidationResult());
        }

        private IndexerResource Resource(bool redirect)
        {
            return new IndexerResource
            {
                Name = "Example",
                Implementation = "Newznab",
                ImplementationName = "Newznab",
                ConfigContract = nameof(NewznabSettings),
                Enable = true,
                Redirect = redirect,
                Fields = SchemaBuilder.ToSchema(_settings)
            };
        }

        [TestCase(false)]
        [TestCase(true)]
        public void api_settings_test_accepts_either_usenet_redirect_setting(bool redirect)
        {
            Subject.Test(Resource(redirect)).Should().Be("{}");

            Mocker.GetMock<IIndexerFactory>().Verify(x => x.Test(It.Is<IndexerDefinition>(d => d.Redirect == redirect && ((NewznabSettings)d.Settings).BaseUrl == _settings.BaseUrl)), Times.Once());
        }

        [Test]
        public void api_settings_test_still_rejects_invalid_settings()
        {
            _settings.BaseUrl = "not a URL";
            Func<object> action = () => Subject.Test(Resource(false));

            action.Should().Throw<ValidationException>().Which.Errors.Should().Contain(x => x.PropertyName == "BaseUrl");
            Mocker.GetMock<IIndexerFactory>().Verify(x => x.Test(It.IsAny<IndexerDefinition>()), Times.Never());
        }

        [Test]
        public void api_settings_update_preserves_false_through_mapping_and_save()
        {
            IndexerDefinition saved = null;
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.Update(It.IsAny<IndexerDefinition>()))
                .Callback<IndexerDefinition>(definition => saved = definition);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.Get(1)).Returns(() => saved);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.SetProviderCharacteristics(It.IsAny<IndexerDefinition>()))
                .Callback<IndexerDefinition>(definition => definition.Capabilities = new IndexerCapabilities());
            var resource = Resource(false);
            resource.Id = 1;

            Subject.UpdateProvider(resource, forceSave: true);

            saved.Should().NotBeNull();
            saved.Redirect.Should().BeFalse();
            Subject.GetResourceById(1).Redirect.Should().BeFalse();
        }
    }
}
