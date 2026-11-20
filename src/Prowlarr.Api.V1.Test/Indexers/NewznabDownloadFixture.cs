using System;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Moq;
using NUnit.Framework;
using NzbDrone.Api.V1.Indexers;
using NzbDrone.Core.Download;
using NzbDrone.Core.Exceptions;
using NzbDrone.Core.Indexers;
using NzbDrone.Test.Common;
using CoreHttp = NzbDrone.Common.Http;

namespace NzbDrone.Api.Test.Indexers
{
    [TestFixture]
    public class NewznabDownloadFixture : TestBase<NewznabController>
    {
        private const string DownloadUrl = "https://indexer.example/download/123";
        private readonly byte[] _bytes = { 1, 2, 3, 4 };
        private IndexerDefinition _definition;

        [SetUp]
        public void Setup()
        {
            _definition = new IndexerDefinition { Id = 1, Enable = true, Redirect = false };
            var indexer = Mocker.GetMock<IIndexer>();
            indexer.SetupGet(x => x.Definition).Returns(_definition);
            indexer.SetupGet(x => x.Protocol).Returns(DownloadProtocol.Usenet);
            indexer.SetupGet(x => x.SupportsRedirect).Returns(true);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.Get(1)).Returns(_definition);
            Mocker.GetMock<IIndexerFactory>().Setup(x => x.GetInstance(_definition)).Returns(indexer.Object);
            Mocker.GetMock<IIndexerStatusService>().Setup(x => x.GetBlockedProviders()).Returns([]);
            Mocker.GetMock<IDownloadMappingService>().Setup(x => x.ConvertToNormalLink("protected")).Returns(DownloadUrl);
            Mocker.GetMock<IDownloadService>()
                .Setup(x => x.DownloadReport(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"))
                .ReturnsAsync(_bytes);
            Subject.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
            Subject.HttpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
        }

        [TestCase(false, true)]
        [TestCase(false, false)]
        [TestCase(true, false)]
        public async Task usenet_without_supported_redirect_returns_nzb_bytes(bool redirect, bool supportsRedirect)
        {
            _definition.Redirect = redirect;
            Mocker.GetMock<IIndexer>().SetupGet(x => x.SupportsRedirect).Returns(supportsRedirect);

            var result = await Subject.GetDownload(1, "protected", "Some%20Release");

            result.Should().BeOfType<FileContentResult>();
            var file = (FileContentResult)result;
            file.FileContents.Should().Equal(_bytes);
            file.ContentType.Should().Be("application/x-nzb");
            file.FileDownloadName.Should().Be("Some Release.nzb");
            Mocker.GetMock<IDownloadService>().Verify(x => x.DownloadReport(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"), Times.Once());
            Mocker.GetMock<IDownloadService>().Verify(x => x.RecordRedirect(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()), Times.Never());
        }

        [TestCase(DownloadProtocol.Usenet)]
        [TestCase(DownloadProtocol.Torrent)]
        public async Task redirect_records_download_without_fetching(DownloadProtocol protocol)
        {
            _definition.Redirect = true;
            Mocker.GetMock<IIndexer>().SetupGet(x => x.Protocol).Returns(protocol);

            var result = (RedirectResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.Url.Should().Be(DownloadUrl);
            result.Permanent.Should().BeTrue();
            Mocker.GetMock<IDownloadService>().Verify(x => x.RecordRedirect(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"), Times.Once());
            Mocker.GetMock<IDownloadService>().Verify(x => x.DownloadReport(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()), Times.Never());
        }

        [TestCase(false, true)]
        [TestCase(true, false)]
        public async Task torrent_without_supported_redirect_returns_torrent_bytes(bool redirect, bool supportsRedirect)
        {
            _definition.Redirect = redirect;
            Mocker.GetMock<IIndexer>().SetupGet(x => x.Protocol).Returns(DownloadProtocol.Torrent);
            Mocker.GetMock<IIndexer>().SetupGet(x => x.SupportsRedirect).Returns(supportsRedirect);

            var result = (FileContentResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.FileContents.Should().Equal(_bytes);
            result.ContentType.Should().Be("application/x-bittorrent");
            result.FileDownloadName.Should().Be("Some Release.torrent");
        }

        [Test]
        public async Task torrent_magnet_response_still_redirects()
        {
            const string magnet = "magnet:?xt=urn:btih:123";
            Mocker.GetMock<IIndexer>().SetupGet(x => x.Protocol).Returns(DownloadProtocol.Torrent);
            Mocker.GetMock<IDownloadService>()
                .Setup(x => x.DownloadReport(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"))
                .ReturnsAsync(Encoding.UTF8.GetBytes(magnet));

            var result = (RedirectResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.Url.Should().Be(magnet);
            result.Permanent.Should().BeTrue();
        }

        [Test]
        public async Task unavailable_usenet_release_returns_410()
        {
            Mocker.GetMock<IDownloadService>()
                .Setup(x => x.DownloadReport(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"))
                .ThrowsAsync(new ReleaseUnavailableException("removed"));

            var result = (ContentResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.StatusCode.Should().Be(410);
            result.Content.Should().Contain("removed");
        }

        [Test]
        public async Task rate_limited_usenet_download_preserves_retry_after()
        {
            var request = new CoreHttp.HttpRequest(DownloadUrl);
            var response = new CoreHttp.HttpResponse(request, new CoreHttp.HttpHeader(), new CookieCollection(), "limited", statusCode: HttpStatusCode.TooManyRequests);
            var exception = new CoreHttp.TooManyRequestsException(request, response, TimeSpan.FromSeconds(90));
            Mocker.GetMock<IDownloadService>()
                .Setup(x => x.DownloadReport(DownloadUrl, 1, It.IsAny<string>(), It.IsAny<string>(), "Some Release"))
                .ThrowsAsync(new ReleaseDownloadException("limited", exception));

            var result = (ContentResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.StatusCode.Should().Be(429);
            result.Content.Should().Contain("limited");
            Subject.Response.Headers.RetryAfter.ToString().Should().Be("90");
        }

        [Test]
        public void new_usenet_indexer_defaults_still_enable_redirect()
        {
            var indexer = Mocker.Resolve<NzbDrone.Core.Indexers.Newznab.Newznab>();

            var definitions = indexer.DefaultDefinitions.OfType<IndexerDefinition>().ToList();

            definitions.Should().NotBeEmpty();
            definitions.Should().OnlyContain(x => x.Redirect && x.SupportsRedirect && x.Protocol == DownloadProtocol.Usenet);
        }

        [Test]
        public async Task disabled_indexer_does_not_fetch()
        {
            _definition.Enable = false;

            var result = (ContentResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.StatusCode.Should().Be(410);
            Mocker.GetMock<IDownloadService>().Verify(x => x.DownloadReport(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()), Times.Never());
        }

        [Test]
        public async Task download_limit_still_blocks_usenet_without_redirect()
        {
            _definition.Settings = new NzbDrone.Core.Indexers.Newznab.NewznabSettings();
            Mocker.GetMock<IIndexerLimitService>().Setup(x => x.AtDownloadLimit(_definition)).Returns(true);
            Mocker.GetMock<IIndexerLimitService>().Setup(x => x.CalculateRetryAfterDownloadLimit(_definition)).Returns(90);

            var result = (ContentResult)await Subject.GetDownload(1, "protected", "Some%20Release");

            result.StatusCode.Should().Be(429);
            Subject.Response.Headers.RetryAfter.ToString().Should().Be("90");
            Mocker.GetMock<IDownloadService>().Verify(x => x.DownloadReport(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()), Times.Never());
            Mocker.GetMock<IDownloadService>().Verify(x => x.RecordRedirect(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()), Times.Never());
        }

        [Test]
        public async Task invalid_link_is_rejected()
        {
            Func<Task> action = async () => await Subject.GetDownload(1, "", "Some Release");

            await action.Should().ThrowAsync<BadRequestException>();
        }
    }
}
